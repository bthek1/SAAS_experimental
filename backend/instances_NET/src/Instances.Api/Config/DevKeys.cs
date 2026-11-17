namespace Instances.Api.Config;

/// <summary>
/// The public half of the published dev key pair (`backend/common/common/dev_keys.py`), for
/// dev, test and e2e only. Anyone can sign with its private half, so prod refuses it.
/// A test checks it still equals the Python file's.
/// </summary>
public static class DevKeys
{
    public const string VerifyingKey = """
        -----BEGIN PUBLIC KEY-----
        MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAn2CvdeWLEnvn900SAuDd
        ktOyhrI3j2c1twkR/YW1caMliZtg1CNwFL0FjmjpZMUYeYOe4/F86T8eeGCjbbaK
        SLRBnBrM8Oa+tU3NBZdr7RDH64OU1lZPMuENdcT8XhkKC6L4q0YGnW+t44C7DH6r
        KDxxRTvumeef5Kif6DaMQ8y9AdY+SXFNJqNhUVW9C5MiApgWRsok50Se/LU3xFjF
        aZ7lKAKSTtWAI7HaNK9lgi2bXKAmTbCYCmI3YXr0FBZMFqetc2zYOfTZkyIHRY0t
        w4pdy07cZzFdZoZaCRIgcgKdWDKW9NZjsl21pEdK11S6YfZWf1Dl5iM1bMq053x2
        2wIDAQAB
        -----END PUBLIC KEY-----

        """;
}
