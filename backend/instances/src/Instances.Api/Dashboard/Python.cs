using System.Globalization;
using System.Numerics;

namespace Instances.Api.Dashboard;

/// <summary>Where the dashboard must round and count time exactly as the Django version did.</summary>
public static class Python
{
    /// <summary>
    /// Python's `round(x, digits)`: the exact value of the double, rounded half to even, so
    /// `round(2.675, 2)` is 2.67 (the double is just under 2.675) and `round(0.125, 2)` 0.12.
    /// </summary>
    public static double Round(double value, int digits)
    {
        if (double.IsNaN(value) || double.IsInfinity(value) || value == 0)
        {
            return value;
        }
        var negative = value < 0;
        var bits = BitConverter.DoubleToInt64Bits(Math.Abs(value));
        var exponent = (int)((bits >> 52) & 0x7FF);
        var mantissa = bits & 0xFFFFFFFFFFFFFL;
        if (exponent == 0)
        {
            exponent = 1;
        }
        else
        {
            mantissa |= 1L << 52;
        }
        exponent -= 1075;

        // value * 10^digits = numerator / denominator, exactly.
        var numerator = new BigInteger(mantissa) * BigInteger.Pow(10, digits);
        var denominator = BigInteger.One;
        if (exponent >= 0)
        {
            numerator <<= exponent;
        }
        else
        {
            denominator <<= -exponent;
        }
        var quotient = BigInteger.DivRem(numerator, denominator, out var remainder);
        var twice = remainder * 2;
        if (twice > denominator || (twice == denominator && !quotient.IsEven))
        {
            quotient += 1;
        }
        var text = quotient.ToString(CultureInfo.InvariantCulture) + "e-" + digits.ToString(CultureInfo.InvariantCulture);
        var rounded = double.Parse(text, NumberStyles.Float, CultureInfo.InvariantCulture);
        return negative ? -rounded : rounded;
    }

    /// <summary>
    /// The instant a wall-clock time names in a zone, as `datetime(..., tzinfo=ZoneInfo(...))`
    /// with `fold=0` reads it: in a repeated hour, the first; in a skipped hour, the offset
    /// from before the change.
    /// </summary>
    public static DateTimeOffset AtWallTime(DateTime wall, TimeZoneInfo zone)
    {
        wall = DateTime.SpecifyKind(wall, DateTimeKind.Unspecified);
        var asUtc = DateTime.SpecifyKind(wall, DateTimeKind.Utc);
        var before = zone.GetUtcOffset(asUtc.AddDays(-1));
        var after = zone.GetUtcOffset(asUtc.AddDays(1));
        bool Valid(TimeSpan offset) => zone.GetUtcOffset(asUtc - offset) == offset;
        var offset = Valid(after) && !Valid(before) ? after : before;
        return new DateTimeOffset(wall, offset);
    }

    /// <summary>`aware - timedelta(days=n)` in Python: the same wall time `n` days earlier.</summary>
    public static DateTimeOffset WallDaysBefore(DateTimeOffset now, int days, TimeZoneInfo zone) =>
        AtWallTime(now.DateTime.AddDays(-days), zone);
}

/// <summary>
/// IANA zone names, as `zoneinfo.ZoneInfo` takes them. Never a path, a directory or a
/// Windows name (the build has no ICU, so .NET cannot map one either).
/// </summary>
public static class Zones
{
    public const int MaxLength = 64;

    public static TimeZoneInfo? Find(string name)
    {
        if (name.Length == 0 || name.StartsWith('/') || name.Contains('\\')
            || name.Split('/').Any(part => part is "" or "." or ".."))
        {
            return null;
        }
        if (!TimeZoneInfo.TryFindSystemTimeZoneById(name, out var zone) || zone.Id != name)
        {
            return null;
        }
        return zone;
    }
}
