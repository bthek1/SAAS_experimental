using System.Data.Common;
using System.Diagnostics;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Routing;
using Microsoft.EntityFrameworkCore.Diagnostics;
using Prometheus;

namespace Instances.Api.Http;

/// <summary>
/// Request and DB metrics with `catalog`'s names, labels and buckets (#44): one Grafana
/// query and `just k6-report` add them to `catalog`'s and the Django version's series.
/// Requests carry the route template as `view`, never the URL, so ids never become label
/// values. Prometheus adds `service` per scrape target.
/// </summary>
public static class MetricNames
{
    /// <summary>The Django version's latency buckets, as `catalog/db.py` copies them.</summary>
    public static readonly double[] LatencyBuckets =
        [0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0, 25.0, 50.0, 75.0];
}

public sealed class RequestMetrics(RequestDelegate next)
{
    static readonly Counter Requests = Metrics.CreateCounter(
        "http_requests_total", "Requests by route template, method and status.", "view", "method", "status");

    static readonly Histogram Latency = Metrics.CreateHistogram(
        "http_request_duration_seconds",
        "Request latency by route template and method.",
        new HistogramConfiguration { LabelNames = ["view", "method"], Buckets = MetricNames.LatencyBuckets });

    public async Task InvokeAsync(HttpContext context)
    {
        var started = Stopwatch.GetTimestamp();
        var failed = false;
        try
        {
            await next(context);
        }
        catch
        {
            failed = true;
            throw;
        }
        finally
        {
            var view = context.GetEndpoint() is RouteEndpoint endpoint
                ? "/" + endpoint.RoutePattern.RawText?.TrimStart('/')
                : "<unmatched>";
            var method = context.Request.Method;
            var status = failed ? 500 : context.Response.StatusCode;
            Requests.WithLabels(view, method, status.ToString(System.Globalization.CultureInfo.InvariantCulture)).Inc();
            Latency.WithLabels(view, method).Observe(Stopwatch.GetElapsedTime(started).TotalSeconds);
        }
    }
}

/// <summary>Every SQL statement EF sends, counted and timed.</summary>
public sealed class DbMetrics : DbCommandInterceptor
{
    static readonly Counter Queries = Metrics.CreateCounter("db_queries_total", "SQL statements executed.");

    static readonly Histogram QueryLatency = Metrics.CreateHistogram(
        "db_query_duration_seconds",
        "SQL statement latency.",
        new HistogramConfiguration { Buckets = MetricNames.LatencyBuckets });

    static void Record(CommandExecutedEventData data)
    {
        Queries.Inc();
        QueryLatency.Observe(data.Duration.TotalSeconds);
    }

    public override ValueTask<DbDataReader> ReaderExecutedAsync(
        DbCommand command, CommandExecutedEventData eventData, DbDataReader result, CancellationToken cancellationToken = default)
    {
        Record(eventData);
        return ValueTask.FromResult(result);
    }

    public override ValueTask<int> NonQueryExecutedAsync(
        DbCommand command, CommandExecutedEventData eventData, int result, CancellationToken cancellationToken = default)
    {
        Record(eventData);
        return ValueTask.FromResult(result);
    }

    public override ValueTask<object?> ScalarExecutedAsync(
        DbCommand command, CommandExecutedEventData eventData, object? result, CancellationToken cancellationToken = default)
    {
        Record(eventData);
        return ValueTask.FromResult(result);
    }

    public override DbDataReader ReaderExecuted(DbCommand command, CommandExecutedEventData eventData, DbDataReader result)
    {
        Record(eventData);
        return result;
    }

    public override int NonQueryExecuted(DbCommand command, CommandExecutedEventData eventData, int result)
    {
        Record(eventData);
        return result;
    }

    public override object? ScalarExecuted(DbCommand command, CommandExecutedEventData eventData, object? result)
    {
        Record(eventData);
        return result;
    }
}
