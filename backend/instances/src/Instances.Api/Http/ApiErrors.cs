using System.Text.Json;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.Filters;

namespace Instances.Api.Http;

/// <summary>
/// DRF's error shapes, which the SPA reads: `{"field": ["message"]}` for validation (400),
/// `{"detail": "message"}` for everything else.
/// </summary>
public class ApiException(int status, object body) : Exception(status.ToString(System.Globalization.CultureInfo.InvariantCulture))
{
    public int Status { get; } = status;
    public object Body { get; } = body;

    public static ApiException Detail(int status, string detail) => new(status, new Dictionary<string, string> { ["detail"] = detail });

    public static ApiException NotFound() => Detail(404, "Not found.");
}

/// <summary>Field errors, gathered so every bad field is reported at once, as DRF does.</summary>
public sealed class FieldErrors
{
    readonly Dictionary<string, List<string>> _errors = [];

    public bool Any => _errors.Count > 0;

    public void Add(string field, string message)
    {
        if (!_errors.TryGetValue(field, out var messages))
        {
            _errors[field] = messages = [];
        }
        messages.Add(message);
    }

    public bool Has(string field) => _errors.ContainsKey(field);

    public void ThrowIfAny()
    {
        if (Any)
        {
            throw new ApiException(400, _errors);
        }
    }

    public static ApiException One(string field, string message)
    {
        var errors = new FieldErrors();
        errors.Add(field, message);
        return new ApiException(400, errors._errors);
    }
}

public static class Messages
{
    public const string Required = "This field is required.";
    public const string NotNull = "This field may not be null.";
    public const string NotBlank = "This field may not be blank.";
    public const string Unavailable = "This action is temporarily unavailable. Please try again.";
    public const string NotAuthenticated = "Authentication credentials were not provided.";
    public const string Forbidden = "You do not have permission to perform this action.";

    public static string DoesNotExist(string value) => $"Invalid pk \"{value}\" - object does not exist.";

    public static string NotAValidUuid(string value) => $"“{value}” is not a valid UUID.";

    public static string MethodNotAllowed(string method) => $"Method \"{method}\" not allowed.";
}

/// <summary>Turns an <see cref="ApiException"/> from any controller into its JSON body.</summary>
public sealed class ApiExceptionFilter : IExceptionFilter
{
    public void OnException(ExceptionContext context)
    {
        if (context.Exception is ApiException api)
        {
            context.Result = new ApiResult(api.Status, api.Body);
            context.ExceptionHandled = true;
        }
    }
}

/// <summary>A body serialized with <see cref="ApiJson.Options"/>, or raw bytes already encoded.</summary>
public sealed class ApiResult(int status, object? body) : IActionResult
{
    public async Task ExecuteResultAsync(ActionContext context)
    {
        var response = context.HttpContext.Response;
        response.StatusCode = status;
        if (body is null)
        {
            return;
        }
        response.ContentType = "application/json";
        var bytes = body as byte[] ?? JsonSerializer.SerializeToUtf8Bytes(body, body.GetType(), ApiJson.Options);
        response.ContentLength = bytes.Length;
        await response.Body.WriteAsync(bytes);
    }
}
