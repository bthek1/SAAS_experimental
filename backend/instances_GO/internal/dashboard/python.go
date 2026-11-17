package dashboard

import (
	"fmt"
	"math"
	"math/big"
	"strconv"
	"strings"
	"time"
	"unicode/utf8"
)

// Round is Python's `round(x, digits)`: the exact value of the double, rounded half to
// even, so `round(2.675, 2)` is 2.67 (the double is just under 2.675) and `round(0.125, 2)`
// 0.12. As instances_NET's Dashboard/Python.cs.
func Round(value float64, digits int) float64 {
	if math.IsNaN(value) || math.IsInf(value, 0) || value == 0 {
		return value
	}
	negative := value < 0
	exact := new(big.Rat).SetFloat64(math.Abs(value))
	exact.Mul(exact, new(big.Rat).SetInt(new(big.Int).Exp(big.NewInt(10), big.NewInt(int64(digits)), nil)))
	quotient, remainder := new(big.Int).QuoRem(exact.Num(), exact.Denom(), new(big.Int))
	twice := new(big.Int).Lsh(remainder, 1)
	switch twice.Cmp(exact.Denom()) {
	case 1:
		quotient.Add(quotient, big.NewInt(1))
	case 0:
		if quotient.Bit(0) == 1 {
			quotient.Add(quotient, big.NewInt(1))
		}
	}
	rounded, _ := strconv.ParseFloat(fmt.Sprintf("%se-%d", quotient.String(), digits), 64)
	if negative {
		return -rounded
	}
	return rounded
}

// AtWallTime is the instant a wall-clock time names in a zone, as
// `datetime(..., tzinfo=ZoneInfo(...))` with `fold=0` reads it: in a repeated hour, the
// first; in a skipped hour, the offset from before the change. The result carries that
// offset, so it prints as Python would.
func AtWallTime(year int, month time.Month, day, hour, minute, second, nanosecond int, zone *time.Location) time.Time {
	asUTC := time.Date(year, month, day, hour, minute, second, nanosecond, time.UTC)
	offsetAt := func(instant time.Time) int { _, offset := instant.In(zone).Zone(); return offset }
	before := offsetAt(asUTC.Add(-24 * time.Hour))
	after := offsetAt(asUTC.Add(24 * time.Hour))
	valid := func(offset int) bool { return offsetAt(asUTC.Add(-time.Duration(offset)*time.Second)) == offset }
	offset := before
	if valid(after) && !valid(before) {
		offset = after
	}
	return asUTC.Add(-time.Duration(offset) * time.Second).In(time.FixedZone("", offset))
}

// WallDaysBefore is `aware - timedelta(days=n)` in Python: the same wall time n days earlier.
func WallDaysBefore(now time.Time, days int, zone *time.Location) time.Time {
	wall := time.Date(now.Year(), now.Month(), now.Day(), now.Hour(), now.Minute(), now.Second(), now.Nanosecond(),
		time.UTC).AddDate(0, 0, -days)
	return AtWallTime(wall.Year(), wall.Month(), wall.Day(), wall.Hour(), wall.Minute(), wall.Second(),
		wall.Nanosecond(), zone)
}

// MaxZoneLength is the longest `tz` accepted.
const MaxZoneLength = 64

// FindZone takes IANA zone names, as `zoneinfo.ZoneInfo` does. Never a path, a directory,
// a Windows name, or Go's "Local".
func FindZone(name string) *time.Location {
	if name == "" || name == "Local" || strings.HasPrefix(name, "/") || strings.Contains(name, `\`) ||
		utf8.RuneCountInString(name) > MaxZoneLength {
		return nil
	}
	for _, part := range strings.Split(name, "/") {
		if part == "" || part == "." || part == ".." {
			return nil
		}
	}
	zone, err := time.LoadLocation(name)
	if err != nil || zone.String() != name {
		return nil
	}
	return zone
}
