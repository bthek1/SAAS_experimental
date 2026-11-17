package server

import (
	"context"
	"crypto/rsa"
	"crypto/subtle"
	"errors"
	"net/http"
	"strings"

	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"instances/internal/httpx"
)

// Auth is who is calling, without a user table (#13). `catalog` signs RS256 access tokens
// with simplejwt's claims; the public key is all it takes to check one. What a token
// cannot say is whether its owner was deactivated after it was issued, so BlockedOwner is
// checked here, before any handler, and so before any cached read.
type Auth struct {
	key  *rsa.PublicKey
	pool *pgxpool.Pool
}

// NewAuth reads the verifying key, a PEM.
func NewAuth(verifyingKey string, pool *pgxpool.Pool) (*Auth, error) {
	key, err := jwt.ParseRSAPublicKeyFromPEM([]byte(verifyingKey))
	if err != nil {
		return nil, err
	}
	return &Auth{key: key, pool: pool}, nil
}

var errBlocked = errors.New("blocked")

// Owner is the token's owner, or the 401 JwtBearer's challenge writes.
func (a *Auth) Owner(r *http.Request) (uuid.UUID, error) {
	header, present := r.Header["Authorization"]
	raw := ""
	if present && len(header) > 0 {
		scheme, rest, ok := strings.Cut(header[0], " ")
		if ok && strings.EqualFold(scheme, "Bearer") {
			raw = strings.TrimSpace(rest)
		}
	}
	if raw == "" {
		return uuid.UUID{}, challenge(present, false)
	}
	owner, err := a.verify(r.Context(), raw)
	if err != nil {
		return uuid.UUID{}, challenge(true, errors.Is(err, errBlocked))
	}
	return owner, nil
}

func (a *Auth) verify(ctx context.Context, raw string) (uuid.UUID, error) {
	claims := jwt.MapClaims{}
	_, err := jwt.ParseWithClaims(raw, claims, func(*jwt.Token) (any, error) { return a.key, nil },
		jwt.WithValidMethods([]string{"RS256"}),
		jwt.WithExpirationRequired(),
		// simplejwt allows no leeway.
		jwt.WithLeeway(0),
	)
	if err != nil {
		return uuid.UUID{}, err
	}
	if tokenType, _ := claims["token_type"].(string); tokenType != "access" {
		return uuid.UUID{}, errors.New("not an access token")
	}
	if jti, _ := claims["jti"].(string); jti == "" {
		return uuid.UUID{}, errors.New("no jti")
	}
	userID, ok := claims["user_id"].(string)
	if !ok {
		return uuid.UUID{}, errors.New("no user id")
	}
	owner, ok := ParseGUID(userID)
	if !ok {
		return uuid.UUID{}, errors.New("no user id")
	}
	var blocked bool
	err = a.pool.QueryRow(ctx,
		`SELECT EXISTS (SELECT 1 FROM questionnaires_blockedowner WHERE owner_id = $1 AND blocked)`,
		owner).Scan(&blocked)
	if err != nil {
		return uuid.UUID{}, err
	}
	if blocked {
		return uuid.UUID{}, errBlocked
	}
	return owner, nil
}

// challenge is the 401: inactive, a token that is not valid, or none at all.
func challenge(sentSomething, blocked bool) error {
	switch {
	case blocked:
		return &challengeError{map[string]string{"detail": "User is inactive", "code": "user_inactive"}}
	case sentSomething:
		return &challengeError{map[string]string{
			"detail": "Given token not valid for any token type", "code": "token_not_valid",
		}}
	}
	return &challengeError{map[string]string{"detail": httpx.MsgNotAuthenticated}}
}

type challengeError struct{ body map[string]string }

func (c *challengeError) Error() string { return "401" }

// PeerTokenValid is `/internal/`'s check: `catalog`'s own bearer token, compared in
// constant time. The gateway never routes `/internal/`.
func PeerTokenValid(r *http.Request, token string) bool {
	if token == "" {
		return false
	}
	supplied := []byte(r.Header.Get("Authorization"))
	expected := []byte("Bearer " + token)
	return subtle.ConstantTimeCompare(supplied, expected) == 1
}
