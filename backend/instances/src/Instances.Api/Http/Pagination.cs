using System.Text;
using Microsoft.AspNetCore.Http;

namespace Instances.Api.Http;

public sealed record Page<T>(int Count, string? Next, string? Previous, IReadOnlyList<T> Results);

/// <summary>
/// DRF's `PageNumberPagination` as `common.pagination.StandardPagination` sets it up (#10):
/// `?page=` and `?page_size=` (default 25, at most 100), absolute links on the request's
/// own host (the gateway passes it through), query keys sorted as DRF's links sort them.
/// </summary>
public sealed class Pagination
{
    public const int DefaultPageSize = 25;
    public const int MaxPageSize = 100;

    public int Number { get; }
    public int Size { get; }

    Pagination(int number, int size)
    {
        Number = number;
        Size = size;
    }

    public int Skip => (Number - 1) * Size;

    /// <summary>Reads the query. A page that cannot exist is checked in <see cref="Build{T}"/>.</summary>
    public static Pagination From(HttpRequest request)
    {
        var size = DefaultPageSize;
        if (request.Query.TryGetValue("page_size", out var rawSize)
            && int.TryParse(rawSize.ToString().Trim(), out var parsedSize) && parsedSize > 0)
        {
            size = Math.Min(parsedSize, MaxPageSize);
        }
        var number = 1;
        if (request.Query.TryGetValue("page", out var rawPage))
        {
            // Not a positive number: Django's paginator says "Invalid page".
            if (!int.TryParse(rawPage.ToString().Trim(), out number) || number < 1)
            {
                throw ApiException.Detail(404, "Invalid page.");
            }
        }
        return new Pagination(number, size);
    }

    public Page<T> Build<T>(HttpRequest request, int count, IReadOnlyList<T> results)
    {
        var pages = Math.Max(1, (count + Size - 1) / Size);
        if (Number > pages)
        {
            throw ApiException.Detail(404, "Invalid page.");
        }
        var next = Number < pages ? Link(request, Number + 1) : null;
        var previous = Number > 1 ? Link(request, Number - 1) : null;
        return new Page<T>(count, next, previous, results);
    }

    /// <summary>DRF's replace_query_param, or remove_query_param for page 1.</summary>
    static string Link(HttpRequest request, int page)
    {
        var query = new SortedDictionary<string, List<string>>(StringComparer.Ordinal);
        foreach (var (key, values) in request.Query)
        {
            query[key] = values.Select(v => v ?? "").ToList();
        }
        if (page == 1)
        {
            query.Remove("page");
        }
        else
        {
            query["page"] = [page.ToString(System.Globalization.CultureInfo.InvariantCulture)];
        }
        var builder = new StringBuilder();
        builder.Append(request.Scheme).Append("://").Append(request.Host.Value)
            .Append(request.PathBase.Value).Append(request.Path.Value);
        var first = true;
        foreach (var (key, values) in query)
        {
            foreach (var value in values)
            {
                builder.Append(first ? '?' : '&').Append(QuotePlus(key)).Append('=').Append(QuotePlus(value));
                first = false;
            }
        }
        return builder.ToString();
    }

    /// <summary>Python's `urllib.parse.quote_plus`.</summary>
    public static string QuotePlus(string value)
    {
        var builder = new StringBuilder();
        foreach (var b in Encoding.UTF8.GetBytes(value))
        {
            var c = (char)b;
            if (c is (>= 'A' and <= 'Z') or (>= 'a' and <= 'z') or (>= '0' and <= '9') or '_' or '.' or '-' or '~')
            {
                builder.Append(c);
            }
            else if (c == ' ')
            {
                builder.Append('+');
            }
            else
            {
                builder.Append('%').Append(b.ToString("X2", System.Globalization.CultureInfo.InvariantCulture));
            }
        }
        return builder.ToString();
    }
}
