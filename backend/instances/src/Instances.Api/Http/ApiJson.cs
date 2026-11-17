using System.Globalization;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Instances.Api.Http;

/// <summary>
/// JSON as DRF wrote it, since the SPA and the parity suite (#40) read it: camelCase names,
/// timestamps as `isoformat()` (microseconds when there are any, `Z` for a zero offset),
/// and stored JSON passed through exactly as stored.
/// </summary>
public static class ApiJson
{
    public static readonly JsonSerializerOptions Options = Create();

    static JsonSerializerOptions Create()
    {
        var options = new JsonSerializerOptions
        {
            PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
            DictionaryKeyPolicy = null,
            DefaultIgnoreCondition = JsonIgnoreCondition.Never,
            Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
        };
        options.Converters.Add(new UtcTimeConverter());
        options.Converters.Add(new ZonedTimeConverter());
        options.Converters.Add(new DateOnlyConverter());
        options.Converters.Add(new RawJsonConverter());
        options.MakeReadOnly(populateMissingResolver: true);
        return options;
    }

    public static byte[] Serialize<T>(T value) => JsonSerializer.SerializeToUtf8Bytes(value, Options);

    /// <summary>Python's `datetime.isoformat()`, then DRF's `+00:00` to `Z`.</summary>
    public static string Format(DateTimeOffset value)
    {
        var micros = value.Ticks % TimeSpan.TicksPerSecond / 10;
        var text = value.ToString("yyyy-MM-dd'T'HH:mm:ss", CultureInfo.InvariantCulture);
        if (micros != 0)
        {
            text += "." + micros.ToString("D6", CultureInfo.InvariantCulture);
        }
        if (value.Offset == TimeSpan.Zero)
        {
            return text + "Z";
        }
        var offset = value.Offset;
        var sign = offset < TimeSpan.Zero ? "-" : "+";
        offset = offset.Duration();
        return $"{text}{sign}{offset.Hours:D2}:{offset.Minutes:D2}";
    }

    public static string Format(DateTime utc) => Format(new DateTimeOffset(DateTime.SpecifyKind(utc, DateTimeKind.Utc)));

    /// <summary>Now, to the microsecond Postgres keeps, so a response shows what was stored.</summary>
    public static DateTime UtcNow()
    {
        var now = DateTime.UtcNow;
        return new DateTime(now.Ticks - now.Ticks % 10, DateTimeKind.Utc);
    }

    sealed class UtcTimeConverter : JsonConverter<DateTime>
    {
        public override DateTime Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options) =>
            throw new NotSupportedException();

        public override void Write(Utf8JsonWriter writer, DateTime value, JsonSerializerOptions options) =>
            writer.WriteStringValue(Format(value));
    }

    sealed class ZonedTimeConverter : JsonConverter<DateTimeOffset>
    {
        public override DateTimeOffset Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options) =>
            throw new NotSupportedException();

        public override void Write(Utf8JsonWriter writer, DateTimeOffset value, JsonSerializerOptions options) =>
            writer.WriteStringValue(Format(value));
    }

    sealed class DateOnlyConverter : JsonConverter<DateOnly>
    {
        public override DateOnly Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options) =>
            throw new NotSupportedException();

        public override void Write(Utf8JsonWriter writer, DateOnly value, JsonSerializerOptions options) =>
            writer.WriteStringValue(value.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture));
    }

    sealed class RawJsonConverter : JsonConverter<RawJson>
    {
        public override RawJson Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
        {
            using var document = JsonDocument.ParseValue(ref reader);
            return new RawJson(document.RootElement.GetRawText());
        }

        public override void Write(Utf8JsonWriter writer, RawJson value, JsonSerializerOptions options) =>
            writer.WriteRawValue(value.Text, skipInputValidation: true);
    }
}

/// <summary>JSON text from a `jsonb` column, or from a request, written back as is.</summary>
public readonly record struct RawJson(string Text)
{
    public static readonly RawJson EmptyObject = new("{}");

    public static RawJson From(JsonElement element) => new(element.GetRawText());
}
