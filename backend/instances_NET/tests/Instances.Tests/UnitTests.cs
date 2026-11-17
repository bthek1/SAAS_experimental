using System.Text.RegularExpressions;
using Instances.Api.Config;
using Instances.Api.Dashboard;
using Instances.Api.Http;
using Instances.Tests.Support;

namespace Instances.Tests;

public sealed class SettingsTests
{
    static Dictionary<string, string> Prod(string profile = "prod") => new()
    {
        ["SETTINGS"] = profile,
        ["INSTANCES_DATABASE_URL"] = "postgres://u:p@db:5432/instancesdb",
        ["JWT_VERIFYING_KEY"] = "-----BEGIN PUBLIC KEY-----\\nnot-the-dev-key\\n-----END PUBLIC KEY-----\\n",
        ["CATALOG_TO_INSTANCES_TOKEN"] = "in",
        ["INSTANCES_TO_CATALOG_TOKEN"] = "out",
        ["CACHE_REDIS_URL"] = "redis://cache:6379/1",
        ["ALLOWED_HOSTS"] = "192.168.2.246,localhost",
    };

    [Fact]
    public void Prod_reads_its_secrets_and_turns_pem_escapes_into_lines()
    {
        var settings = Settings.Load(Prod());
        Assert.Contains("\nnot-the-dev-key\n", settings.JwtVerifyingKey);
        Assert.True(settings.HttpsRedirect);
        Assert.False(settings.LoadTest);
    }

    [Fact]
    public void Prod_refuses_the_published_dev_key()
    {
        var environment = Prod();
        environment["JWT_VERIFYING_KEY"] = DevKeys.VerifyingKey;
        Assert.Contains("dev key", Assert.Throws<SettingsException>(() => Settings.Load(environment)).Message);
    }

    [Theory]
    [InlineData("JWT_VERIFYING_KEY")]
    [InlineData("CATALOG_TO_INSTANCES_TOKEN")]
    [InlineData("CACHE_REDIS_URL")]
    [InlineData("ALLOWED_HOSTS")]
    public void Prod_needs(string name)
    {
        var environment = Prod();
        environment.Remove(name);
        Assert.Throws<SettingsException>(() => Settings.Load(environment));
    }

    [Fact]
    public void Loadtest_is_prod_over_plain_http()
    {
        var settings = Settings.Load(Prod("loadtest"));
        Assert.False(settings.HttpsRedirect);
        Assert.True(settings.LoadTest);
    }

    [Theory]
    [InlineData("example.com")]
    [InlineData("8.8.8.8")]
    public void Loadtest_refuses_a_public_host(string host)
    {
        var environment = Prod("loadtest");
        environment["ALLOWED_HOSTS"] = $"localhost,{host}";
        Assert.Throws<SettingsException>(() => Settings.Load(environment));
    }

    [Fact]
    public void Tests_always_trust_the_dev_key_and_never_cache()
    {
        var settings = Settings.Load(new Dictionary<string, string>
        {
            ["SETTINGS"] = "test",
            ["INSTANCES_DATABASE_URL"] = "postgres://u:p@db/x",
            ["JWT_VERIFYING_KEY"] = "a developer's key",
            ["CACHE_ENABLED"] = "true",
        });
        Assert.Equal(DevKeys.VerifyingKey, settings.JwtVerifyingKey);
        Assert.False(settings.CacheEnabled);
        Assert.Equal("test-catalog-to-instances", settings.InboundPeerToken);
    }

    [Fact]
    public void Dev_reads_a_key_from_the_environment_and_falls_back_to_the_dev_key()
    {
        var dev = new Dictionary<string, string> { ["SETTINGS"] = "dev", ["INSTANCES_DATABASE_URL"] = "postgres://u:p@db/x" };
        Assert.Equal(DevKeys.VerifyingKey, Settings.Load(dev).JwtVerifyingKey);
        dev["JWT_VERIFYING_KEY"] = "a developer's key";
        Assert.Equal("a developer's key", Settings.Load(dev).JwtVerifyingKey);
    }

    [Fact]
    public void An_unknown_profile_is_refused() =>
        Assert.Throws<SettingsException>(() => Settings.Load(new Dictionary<string, string> { ["SETTINGS"] = "staging" }));

    [Fact]
    public void The_dev_key_is_the_one_python_publishes()
    {
        var source = File.ReadAllText(Paths.Backend("common", "common", "dev_keys.py"));
        var pem = Regex.Match(source, "DEV_VERIFYING_KEY = \"\"\"(?<pem>.*?)\"\"\"", RegexOptions.Singleline).Groups["pem"].Value;
        Assert.Equal(pem.Trim(), DevKeys.VerifyingKey.Trim());
    }

    [Fact]
    public void Dotenv_lines()
    {
        var values = DotEnv.Parse(["# comment", "A=1", "export B = two ", "C=\"quoted value\"", "D='x'", "bad line"]);
        Assert.Equal(new Dictionary<string, string> { ["A"] = "1", ["B"] = "two", ["C"] = "quoted value", ["D"] = "x" }, values);
    }
}

public sealed class PythonTests
{
    [Theory]
    [InlineData(2.675, 2, 2.67)]
    [InlineData(0.125, 2, 0.12)]
    [InlineData(0.375, 2, 0.38)]
    [InlineData(1.25, 1, 1.2)]
    [InlineData(22.0 / 3, 2, 7.33)]
    [InlineData(2.0 / 3, 4, 0.6667)]
    [InlineData(-2.5, 0, -2.0)]
    [InlineData(250.0, 2, 250.0)]
    public void Round_is_pythons(double value, int digits, double expected) =>
        Assert.Equal(expected, Python.Round(value, digits));

    [Fact]
    public void A_wall_time_in_a_repeated_hour_is_the_first()
    {
        var zone = TimeZoneInfo.FindSystemTimeZoneById("America/New_York");
        // 2026-11-01 01:30 happens twice in New York: first at -04:00.
        Assert.Equal(TimeSpan.FromHours(-4), Python.AtWallTime(new DateTime(2026, 11, 1, 1, 30, 0), zone).Offset);
    }

    [Fact]
    public void A_wall_time_in_a_skipped_hour_keeps_the_offset_from_before()
    {
        var zone = TimeZoneInfo.FindSystemTimeZoneById("America/New_York");
        // 2026-03-08 02:30 never happens in New York; Python's fold=0 reads it at -05:00.
        Assert.Equal(TimeSpan.FromHours(-5), Python.AtWallTime(new DateTime(2026, 3, 8, 2, 30, 0), zone).Offset);
    }

    [Fact]
    public void A_window_starts_at_local_midnight_with_that_days_offset()
    {
        var zone = TimeZoneInfo.FindSystemTimeZoneById("America/New_York");
        var now = new DateTimeOffset(2026, 11, 13, 1, 0, 0, TimeSpan.FromHours(-5));
        var start = DashboardService.WindowStart(90, now, zone)!.Value;
        Assert.Equal(new DateTimeOffset(2026, 8, 16, 0, 0, 0, TimeSpan.FromHours(-4)), start);
        Assert.Equal("2026-08-16T00:00:00-04:00", ApiJson.Format(start));
    }

    [Theory]
    [InlineData("America/New_York", true)]
    [InlineData("UTC", true)]
    [InlineData("Asia/Kolkata", true)]
    [InlineData("America", false)]
    [InlineData("../../etc/passwd", false)]
    [InlineData("/usr/share/zoneinfo/UTC", false)]
    [InlineData("Eastern Standard Time", false)]
    [InlineData("Nowhere/City", false)]
    public void Zones_are_iana_names_only(string name, bool found) =>
        Assert.Equal(found, Zones.Find(name) is not null);
}

public sealed class WireFormatTests
{
    [Theory]
    [InlineData(0, "2026-01-02T03:04:05Z")]
    [InlineData(1234560, "2026-01-02T03:04:05.123456Z")]
    [InlineData(1000000, "2026-01-02T03:04:05.100000Z")]
    public void Timestamps_are_drf_isoformat(long ticks, string expected) =>
        Assert.Equal(expected, ApiJson.Format(new DateTime(2026, 1, 2, 3, 4, 5, DateTimeKind.Utc).AddTicks(ticks)));

    [Fact]
    public void A_zero_offset_in_any_zone_is_z() =>
        Assert.Equal("2026-01-02T00:00:00Z", ApiJson.Format(new DateTimeOffset(2026, 1, 2, 0, 0, 0, TimeSpan.Zero)));

    [Fact]
    public void A_half_hour_offset() =>
        Assert.Equal("2026-01-02T05:30:00+05:30", ApiJson.Format(new DateTimeOffset(2026, 1, 2, 5, 30, 0, TimeSpan.FromMinutes(330))));

    [Theory]
    [InlineData("abc-_.~", "abc-_.~")]
    [InlineData("a b", "a+b")]
    [InlineData("a/b&c=d", "a%2Fb%26c%3Dd")]
    [InlineData("é", "%C3%A9")]
    public void Links_quote_as_python_does(string value, string expected) =>
        Assert.Equal(expected, Pagination.QuotePlus(value));
}
