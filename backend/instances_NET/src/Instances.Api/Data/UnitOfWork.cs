using Instances.Api.Caching;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Storage;

namespace Instances.Api.Data;

/// <summary>
/// One transaction, and the owners whose cached entries it invalidates. The generations are
/// bumped only after the commit: before it, a reader could cache the old rows under the
/// new generation. A rollback bumps nothing.
/// </summary>
public sealed class UnitOfWork : IAsyncDisposable
{
    readonly IDbContextTransaction _transaction;
    readonly Cache _cache;
    readonly HashSet<Guid> _bumps = [];

    UnitOfWork(IDbContextTransaction transaction, Cache cache)
    {
        _transaction = transaction;
        _cache = cache;
    }

    public static async Task<UnitOfWork> Begin(InstancesDb db, Cache cache) =>
        new(await db.Database.BeginTransactionAsync(), cache);

    public void BumpOwnerGenerationAfterCommit(Guid ownerId) => _bumps.Add(ownerId);

    public async Task Commit()
    {
        await _transaction.CommitAsync();
        foreach (var ownerId in _bumps)
        {
            await _cache.BumpOwnerGeneration(ownerId);
        }
    }

    public ValueTask DisposeAsync() => _transaction.DisposeAsync();
}
