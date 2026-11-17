using System.Security.Claims;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Instances.Api.Config;
using Instances.Api.Data;
using Instances.Api.Http;
using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.Filters;
using Microsoft.EntityFrameworkCore;
using Microsoft.IdentityModel.JsonWebTokens;
using Microsoft.IdentityModel.Tokens;

namespace Instances.Api.Auth;

/// <summary>
/// Who is calling, without a user table (#13). `catalog` signs RS256 access tokens with
/// simplejwt's claims; the public key is all it takes to check one. What a token cannot say
/// is whether its owner was deactivated after it was issued, so `BlockedOwner` is checked
/// here, before any handler, and so before any cached read.
/// </summary>
public static class OwnerAuth
{
    public const string OwnerIdClaim = "owner_id";
    const string UserIdClaim = "user_id";

    public static void Configure(JwtBearerOptions options, Settings settings)
    {
        var rsa = RSA.Create();
        rsa.ImportFromPem(settings.JwtVerifyingKey);
        options.MapInboundClaims = false;
        options.RequireHttpsMetadata = false;
        options.TokenValidationParameters = new TokenValidationParameters
        {
            IssuerSigningKey = new RsaSecurityKey(rsa),
            ValidAlgorithms = [SecurityAlgorithms.RsaSha256],
            ValidateIssuer = false,
            ValidateAudience = false,
            ValidateLifetime = true,
            RequireExpirationTime = true,
            RequireSignedTokens = true,
            // simplejwt allows no leeway.
            ClockSkew = TimeSpan.Zero,
        };
        options.Events = new JwtBearerEvents
        {
            // `/internal/` carries the peer's own token, which is not a JWT.
            OnMessageReceived = context =>
            {
                if (context.Request.Path.StartsWithSegments("/internal"))
                {
                    context.NoResult();
                }
                return Task.CompletedTask;
            },
            OnTokenValidated = OnTokenValidated,
            OnChallenge = OnChallenge,
        };
    }

    static async Task OnTokenValidated(TokenValidatedContext context)
    {
        var token = context.SecurityToken as JsonWebToken;
        if (token is null
            || !token.TryGetPayloadValue<string>("token_type", out var tokenType) || tokenType != "access"
            || !token.TryGetPayloadValue<string>("jti", out var jti) || string.IsNullOrEmpty(jti))
        {
            context.Fail("Given token not valid for any token type");
            return;
        }
        if (!token.TryGetClaim(UserIdClaim, out var userId)
            || userId.ValueType != ClaimValueTypes.String
            || !Guid.TryParse(userId.Value, out var ownerId))
        {
            context.Fail("Token contained no recognizable user id");
            return;
        }
        var db = context.HttpContext.RequestServices.GetRequiredService<InstancesDb>();
        if (await db.BlockedOwners.AnyAsync(b => b.OwnerId == ownerId && b.Blocked))
        {
            context.HttpContext.Items[BlockedKey] = true;
            context.Fail("User is inactive");
            return;
        }
        var identity = new ClaimsIdentity(
            [new Claim(OwnerIdClaim, ownerId.ToString())], JwtBearerDefaults.AuthenticationScheme);
        context.Principal = new ClaimsPrincipal(identity);
    }

    const string BlockedKey = "instances.blocked";

    static async Task OnChallenge(JwtBearerChallengeContext context)
    {
        context.HandleResponse();
        var response = context.Response;
        response.StatusCode = 401;
        response.Headers.WWWAuthenticate = "Bearer realm=\"api\"";
        object body = context.HttpContext.Items.ContainsKey(BlockedKey)
            ? new Dictionary<string, string> { ["detail"] = "User is inactive", ["code"] = "user_inactive" }
            : context.AuthenticateFailure is not null || context.Request.Headers.Authorization.Count > 0
                ? new Dictionary<string, string>
                {
                    ["detail"] = "Given token not valid for any token type",
                    ["code"] = "token_not_valid",
                }
                : new Dictionary<string, string> { ["detail"] = Messages.NotAuthenticated };
        response.ContentType = "application/json";
        await response.Body.WriteAsync(JsonSerializer.SerializeToUtf8Bytes(body, ApiJson.Options));
    }

    public static Guid OwnerId(this ClaimsPrincipal user) =>
        Guid.Parse(user.FindFirstValue(OwnerIdClaim) ?? throw new InvalidOperationException("no owner"));
}

/// <summary>
/// `/internal/` is reached only by the other service, on its own bearer token (one per
/// direction). The gateway never routes it. Anything else is 403, as DRF's permission was.
/// </summary>
[AttributeUsage(AttributeTargets.Class | AttributeTargets.Method)]
public sealed class InternalTokenAttribute : Attribute, IAuthorizationFilter
{
    public void OnAuthorization(AuthorizationFilterContext context)
    {
        var settings = context.HttpContext.RequestServices.GetRequiredService<Settings>();
        var supplied = Encoding.UTF8.GetBytes(context.HttpContext.Request.Headers.Authorization.ToString());
        var expected = Encoding.UTF8.GetBytes($"Bearer {settings.InboundPeerToken}");
        if (settings.InboundPeerToken.Length == 0 || !CryptographicOperations.FixedTimeEquals(supplied, expected))
        {
            context.Result = new ApiResult(403, new Dictionary<string, string> { ["detail"] = Messages.Forbidden });
        }
    }
}
