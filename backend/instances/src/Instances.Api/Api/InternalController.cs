using Instances.Api.Auth;
using Instances.Api.Data;
using Instances.Api.Http;
using Instances.Api.Refs;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace Instances.Api.Api;

/// <summary>What `catalog` may ask of `instances`. Shapes: `backend/contracts/`.</summary>
[AllowAnonymous]
[Route("internal")]
public sealed class InternalController(RefService refs) : ControllerBase
{
    [InternalToken]
    [HttpPost("events")]
    public async Task<IActionResult> Event()
    {
        var body = await Body.Read(Request);
        try
        {
            return new ApiResult(200, new Dictionary<string, string> { ["result"] = await refs.ApplyEvent(body) });
        }
        catch (BadEvent exc)
        {
            // Retrying cannot help a malformed event, so this is not a 5xx.
            throw ApiException.Detail(400, exc.Message);
        }
    }

    [InternalToken]
    [HttpPost("refs/{kind}/{refId:guid}/retire")]
    public async Task<IActionResult> Retire(string kind, Guid refId)
    {
        if (!Kinds.IsKnown(kind))
        {
            throw ApiException.NotFound();
        }
        try
        {
            await refs.Retire(kind, refId);
        }
        catch (RefInUse)
        {
            throw ApiException.Detail(409, "in use");
        }
        return new ApiResult(204, null);
    }

    [HttpGet("health")]
    public IActionResult Health() => new ApiResult(200, new Dictionary<string, string> { ["status"] = "ok" });
}
