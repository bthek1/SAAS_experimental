using Npgsql;

namespace Instances.Api.Data;

/// <summary>`postgres://user:password@host:port/name`, as the Django version read it.</summary>
public static class DatabaseUrl
{
    public static string ToConnectionString(string url, int poolSize)
    {
        var uri = new Uri(url);
        if (uri.Scheme is not ("postgres" or "postgresql" or "pgsql"))
        {
            throw new ArgumentException($"Not a Postgres URL: {uri.Scheme}://...");
        }
        var userInfo = uri.UserInfo.Split(':', 2);
        var builder = new NpgsqlConnectionStringBuilder
        {
            Host = uri.Host,
            Port = uri.IsDefaultPort || uri.Port <= 0 ? 5432 : uri.Port,
            Database = Uri.UnescapeDataString(uri.AbsolutePath.TrimStart('/')),
            Username = Uri.UnescapeDataString(userInfo[0]),
            Password = userInfo.Length > 1 ? Uri.UnescapeDataString(userInfo[1]) : null,
            // Every value is UTC, whatever the server's default (#37).
            Timezone = "UTC",
            MaxPoolSize = poolSize,
            // The LXC databases are SQL_ASCII: ask for UTF-8 explicitly.
            ClientEncoding = "UTF8",
            // No Kerberos anywhere, and the runtime image has no libgssapi to try it with.
            GssEncryptionMode = GssEncryptionMode.Disable,
        };
        foreach (var pair in uri.Query.TrimStart('?').Split('&', StringSplitOptions.RemoveEmptyEntries))
        {
            var parts = pair.Split('=', 2);
            if (parts[0] == "sslmode" && parts.Length == 2)
            {
                builder.SslMode = Enum.Parse<SslMode>(parts[1], ignoreCase: true);
            }
        }
        return builder.ConnectionString;
    }
}
