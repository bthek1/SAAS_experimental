using System.Globalization;
using System.Text.Json;
using Instances.Api.Data;
using Instances.Api.Refs;
using Microsoft.AspNetCore.Http;
using Microsoft.EntityFrameworkCore;

namespace Instances.Api.Http;

/// <summary>
/// The parts of DRF's serializer fields the API relies on, with their messages, so the SPA
/// sees the same `{field: [message]}` bodies it always has.
/// </summary>
public static class Body
{
    /// <summary>The request body as a JSON object; an empty body is `{}`.</summary>
    public static async Task<JsonElement> ReadObject(HttpRequest request)
    {
        var element = await Read(request);
        if (element.ValueKind != JsonValueKind.Object)
        {
            var kind = element.ValueKind switch
            {
                JsonValueKind.Array => "list",
                JsonValueKind.String => "str",
                JsonValueKind.Number => "int",
                JsonValueKind.True or JsonValueKind.False => "bool",
                _ => "NoneType",
            };
            throw FieldErrors.One("non_field_errors", $"Invalid data. Expected a dictionary, but got {kind}.");
        }
        return element;
    }

    /// <summary>The request body as any JSON value; an empty body is `{}`.</summary>
    public static async Task<JsonElement> Read(HttpRequest request)
    {
        using var buffer = new MemoryStream();
        await request.Body.CopyToAsync(buffer);
        if (buffer.Length == 0)
        {
            using var empty = JsonDocument.Parse("{}");
            return empty.RootElement.Clone();
        }
        try
        {
            using var document = JsonDocument.Parse(buffer.ToArray());
            return document.RootElement.Clone();
        }
        catch (JsonException exc)
        {
            throw ApiException.Detail(400, $"JSON parse error - {exc.Message}");
        }
    }

    public static JsonElement? Field(JsonElement body, string name) =>
        body.TryGetProperty(name, out var value) ? value : null;
}

public static class Fields
{
    /// <summary>A model `CharField(max_length=255, blank=True)`: trimmed, never null.</summary>
    public static string? Text(JsonElement? value, string field, FieldErrors errors, int maxLength = 255)
    {
        if (value is not { } element)
        {
            return null;
        }
        string text;
        switch (element.ValueKind)
        {
            case JsonValueKind.String:
                text = element.GetString()!;
                break;
            case JsonValueKind.Number:
                text = element.GetRawText();
                break;
            case JsonValueKind.Null:
                errors.Add(field, Messages.NotNull);
                return null;
            default:
                errors.Add(field, "Not a valid string.");
                return null;
        }
        text = text.Trim();
        if (text.Length > maxLength)
        {
            errors.Add(field, $"Ensure this field has no more than {maxLength} characters.");
            return null;
        }
        return text;
    }

    /// <summary>A `DictField`: any JSON object, kept as its text.</summary>
    public static RawJson? Object(JsonElement? value, string field, FieldErrors errors, bool required)
    {
        if (value is not { } element)
        {
            if (required)
            {
                errors.Add(field, Messages.Required);
            }
            return null;
        }
        switch (element.ValueKind)
        {
            case JsonValueKind.Object:
                return RawJson.From(element);
            case JsonValueKind.Null:
                errors.Add(field, Messages.NotNull);
                return null;
            default:
                errors.Add(field, $"Expected a dictionary of items but got type \"{PythonType(element)}\".");
                return null;
        }
    }

    static readonly HashSet<string> True = ["t", "T", "y", "Y", "yes", "Yes", "YES", "true", "True", "TRUE", "on", "On", "ON", "1"];
    static readonly HashSet<string> False = ["f", "F", "n", "N", "no", "No", "NO", "false", "False", "FALSE", "off", "Off", "OFF", "0"];
    static readonly HashSet<string> Null = ["null", "Null", "NULL", ""];

    /// <summary>A query string `BooleanField(allow_null=True)`.</summary>
    public static bool? Boolean(string? value, string field, FieldErrors errors)
    {
        if (value is null || Null.Contains(value))
        {
            return null;
        }
        if (True.Contains(value))
        {
            return true;
        }
        if (False.Contains(value))
        {
            return false;
        }
        errors.Add(field, "Must be a valid boolean.");
        return null;
    }

    public static string PythonType(JsonElement element) => element.ValueKind switch
    {
        JsonValueKind.Array => "list",
        JsonValueKind.String => "str",
        JsonValueKind.Number => element.TryGetInt64(out _) ? "int" : "float",
        JsonValueKind.True or JsonValueKind.False => "bool",
        JsonValueKind.Object => "dict",
        _ => "NoneType",
    };
}

/// <summary>
/// An owned type's copy, as Django's `OwnedRefField`: only the caller's own. A copy that has
/// not arrived yet is fetched from `catalog` once; `catalog` being unreachable is a 503,
/// since the id may well be valid, where a 400 would tell the owner their type is gone.
/// </summary>
public sealed class OwnedRefs(InstancesDb db, RefService refs)
{
    public Task<Guid?> Resolve(JsonElement? value, string kind, string field, Guid ownerId, FieldErrors errors, bool required)
    {
        if (value is not { } element)
        {
            if (required)
            {
                errors.Add(field, Messages.Required);
            }
            return Task.FromResult<Guid?>(null);
        }
        // DRF's relational fields take an empty string as null.
        if (element.ValueKind == JsonValueKind.Null
            || (element.ValueKind == JsonValueKind.String && element.GetString() == ""))
        {
            errors.Add(field, Messages.NotNull);
            return Task.FromResult<Guid?>(null);
        }
        if (element.ValueKind != JsonValueKind.String)
        {
            errors.Add(field, $"Incorrect type. Expected pk value, received {Fields.PythonType(element)}.");
            return Task.FromResult<Guid?>(null);
        }
        return Resolve(element.GetString()!, kind, field, ownerId, errors);
    }

    public async Task<Guid?> Resolve(string text, string kind, string field, Guid ownerId, FieldErrors errors)
    {
        if (text == "")
        {
            errors.Add(field, Messages.NotNull);
            return null;
        }
        if (!Guid.TryParse(text, out var refId) || !IsUuidText(text))
        {
            errors.Add(field, Messages.NotAValidUuid(text));
            return null;
        }
        var owner = await OwnerOf(kind, refId);
        if (owner == ownerId)
        {
            return refId;
        }
        // Another owner's copy: nothing `catalog` says would change the answer.
        if (owner is null && await refs.ReadThroughOr503(kind, refId) && await OwnerOf(kind, refId) == ownerId)
        {
            return refId;
        }
        errors.Add(field, Messages.DoesNotExist(text));
        return null;
    }

    Task<Guid?> OwnerOf(string kind, Guid refId) => kind == Kinds.QuestionnaireType
        ? db.QuestionnaireTypeRefs.Where(t => t.Id == refId).Select(t => (Guid?)t.OwnerId).SingleOrDefaultAsync()
        : db.BatteryTypeRefs.Where(t => t.Id == refId).Select(t => (Guid?)t.OwnerId).SingleOrDefaultAsync();

    /// <summary>The spellings Python's `uuid.UUID` reads: hex, with or without dashes or braces.</summary>
    static bool IsUuidText(string text)
    {
        var hex = text.Replace("urn:uuid:", "", StringComparison.OrdinalIgnoreCase).Trim('{', '}').Replace("-", "");
        return hex.Length == 32 && hex.All(Uri.IsHexDigit);
    }
}

public static class Query
{
    public static string? Get(HttpRequest request, string name) =>
        // Django's QueryDict gives the last of repeated values.
        request.Query.TryGetValue(name, out var values) && values.Count > 0 ? values[values.Count - 1] : null;

    public static int ParseInt(string value) => int.Parse(value, CultureInfo.InvariantCulture);
}
