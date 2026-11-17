using System.Net;
using System.Net.Http.Headers;
using System.Text.Json;
using Instances.Api.Config;

namespace Instances.Api.Peers;

/// <summary>The peer gave no usable answer: down, too slow, 5xx, or it refused our token.</summary>
public sealed class PeerUnavailable(string message, Exception? inner = null) : Exception(message, inner);

public interface ICatalogClient
{
    /// <summary>`catalog`'s snapshot of a type, or null if it has no such type.</summary>
    Task<JsonElement?> Fetch(string kind, Guid refId);

    /// <summary>Every snapshot of one kind, page after page.</summary>
    IAsyncEnumerable<JsonElement> Snapshots(string kind);
}

/// <summary>
/// `catalog`'s `/internal/` over HTTP (#13), with short timeouts, so a dead peer never
/// holds a request long. Shapes: `backend/contracts/response.*.json`.
/// </summary>
public sealed class HttpCatalogClient(HttpClient http) : ICatalogClient
{
    static readonly Dictionary<string, string> Slugs = new()
    {
        ["questionnaire_type"] = "questionnaire-types",
        ["battery_type"] = "battery-types",
    };

    public static void Configure(HttpClient http, Settings settings)
    {
        http.BaseAddress = new Uri(settings.CatalogInternalUrl.TrimEnd('/') + "/");
        http.Timeout = settings.PeerConnectTimeout + settings.PeerReadTimeout;
        http.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", settings.OutboundPeerToken);
    }

    public static SocketsHttpHandler Handler(Settings settings) => new()
    {
        ConnectTimeout = settings.PeerConnectTimeout,
        PooledConnectionIdleTimeout = TimeSpan.FromSeconds(30),
    };

    public async Task<JsonElement?> Fetch(string kind, Guid refId)
    {
        using var response = await Send($"internal/{Slugs[kind]}/{refId}/");
        if (response.StatusCode == HttpStatusCode.NotFound)
        {
            return null;
        }
        if (response.StatusCode != HttpStatusCode.OK)
        {
            throw new PeerUnavailable($"fetch: HTTP {(int)response.StatusCode}");
        }
        return await Read(response);
    }

    public async IAsyncEnumerable<JsonElement> Snapshots(string kind)
    {
        string? after = null;
        while (true)
        {
            var path = $"internal/{Slugs[kind]}/" + (after is null ? "" : $"?after={Uri.EscapeDataString(after)}");
            using var response = await Send(path);
            if (response.StatusCode != HttpStatusCode.OK)
            {
                throw new PeerUnavailable($"list: HTTP {(int)response.StatusCode}");
            }
            var page = await Read(response);
            foreach (var snapshot in page.GetProperty("results").EnumerateArray())
            {
                yield return snapshot;
            }
            var next = page.GetProperty("next");
            if (next.ValueKind == JsonValueKind.Null)
            {
                yield break;
            }
            after = next.GetString();
        }
    }

    async Task<HttpResponseMessage> Send(string path)
    {
        HttpResponseMessage response;
        try
        {
            response = await http.GetAsync(path, HttpCompletionOption.ResponseContentRead);
        }
        catch (Exception exc) when (exc is HttpRequestException or TaskCanceledException or IOException)
        {
            throw new PeerUnavailable($"GET /{path}: {exc.Message}", exc);
        }
        var status = (int)response.StatusCode;
        // A refused token is a deployment fault, and retrying can recover from that.
        if (status >= 500 || status is 401 or 403)
        {
            response.Dispose();
            throw new PeerUnavailable($"GET /{path}: HTTP {status}");
        }
        return response;
    }

    static async Task<JsonElement> Read(HttpResponseMessage response)
    {
        try
        {
            using var document = await JsonDocument.ParseAsync(await response.Content.ReadAsStreamAsync());
            return document.RootElement.Clone();
        }
        catch (Exception exc) when (exc is JsonException or IOException or HttpRequestException)
        {
            throw new PeerUnavailable($"unreadable answer: {exc.Message}", exc);
        }
    }
}
