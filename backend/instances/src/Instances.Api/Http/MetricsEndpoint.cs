using Instances.Api.Config;
using Microsoft.AspNetCore.Http;
using Prometheus;

namespace Instances.Api.Http;

/// <summary>
/// Prometheus `/metrics`, for the scraper only (#9). First in the pipeline, before host
/// filtering and any HTTPS redirect, since Prometheus scrapes by IP over plain HTTP. It
/// answers only a direct peer inside METRICS_ALLOWED_CIDRS, never a request that came
/// through a proxy (any forwarding header), so a proxy in front can never make it public.
/// Everyone else gets the same 404 as an unknown path.
/// </summary>
public sealed class MetricsEndpoint(RequestDelegate next, Settings settings)
{
    static readonly string[] ForwardingHeaders = ["X-Forwarded-For", "X-Real-IP", "Forwarded"];

    public async Task InvokeAsync(HttpContext context)
    {
        var path = context.Request.Path.Value ?? "";
        if (path.TrimEnd('/') != "/metrics")
        {
            await next(context);
            return;
        }
        if (!HttpMethods.IsGet(context.Request.Method) || !ScrapeAllowed(context))
        {
            context.Response.StatusCode = 404;
            return;
        }
        context.Response.ContentType = "text/plain; version=0.0.4; charset=utf-8";
        await Metrics.DefaultRegistry.CollectAndExportAsTextAsync(context.Response.Body, context.RequestAborted);
    }

    bool ScrapeAllowed(HttpContext context)
    {
        if (ForwardingHeaders.Any(context.Request.Headers.ContainsKey))
        {
            return false;
        }
        if (context.Connection.RemoteIpAddress is not { } peer)
        {
            return false;
        }
        if (peer.IsIPv4MappedToIPv6)
        {
            peer = peer.MapToIPv4();
        }
        return settings.MetricsAllowedNetworks.Any(network => network.Contains(peer));
    }
}
