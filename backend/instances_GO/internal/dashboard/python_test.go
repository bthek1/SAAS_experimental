package dashboard

import (
	"testing"
	"time"

	"instances/internal/httpx"
)

// The same cases as instances_NET's PythonTests, each checked against Python's round().
func TestRoundIsPythons(t *testing.T) {
	for _, c := range []struct {
		value    float64
		digits   int
		expected float64
	}{
		{2.675, 2, 2.67}, {0.125, 2, 0.12}, {0.375, 2, 0.38}, {1.25, 1, 1.2}, {22.0 / 3, 2, 7.33},
		{2.0 / 3, 4, 0.6667}, {-2.5, 0, -2.0}, {250.0, 2, 250.0}, {0.5, 0, 0}, {1.5, 0, 2},
	} {
		if got := Round(c.value, c.digits); got != c.expected {
			t.Errorf("round(%v, %d) = %v, want %v", c.value, c.digits, got, c.expected)
		}
	}
}

func newYork(t *testing.T) *time.Location {
	zone := FindZone("America/New_York")
	if zone == nil {
		t.Fatal("America/New_York not found")
	}
	return zone
}

func offset(t time.Time) int { _, o := t.Zone(); return o / 3600 }

func TestAWallTimeInARepeatedHourIsTheFirst(t *testing.T) {
	// 2026-11-01 01:30 happens twice in New York: first at -04:00.
	if got := offset(AtWallTime(2026, 11, 1, 1, 30, 0, 0, newYork(t))); got != -4 {
		t.Fatal(got)
	}
}

func TestAWallTimeInASkippedHourKeepsTheOffsetFromBefore(t *testing.T) {
	// 2026-03-08 02:30 never happens in New York; Python's fold=0 reads it at -05:00.
	if got := offset(AtWallTime(2026, 3, 8, 2, 30, 0, 0, newYork(t))); got != -5 {
		t.Fatal(got)
	}
}

func TestAWindowStartsAtLocalMidnightWithThatDaysOffset(t *testing.T) {
	zone := newYork(t)
	now := time.Date(2026, 11, 13, 1, 0, 0, 0, zone)
	days := 90
	start := WindowStart(&days, now, zone)
	if got := httpx.Format(*start); got != "2026-08-16T00:00:00-04:00" {
		t.Fatal(got)
	}
}

func TestWallDaysBeforeKeepsTheWallTime(t *testing.T) {
	zone := newYork(t)
	// A week before 12:00 on 2026-11-05 (-05:00) is 12:00 on 2026-10-29, at -04:00.
	got := WallDaysBefore(time.Date(2026, 11, 5, 12, 0, 0, 0, zone), 7, zone)
	if httpx.Format(got) != "2026-10-29T12:00:00-04:00" {
		t.Fatal(httpx.Format(got))
	}
}

func TestZonesAreIANANamesOnly(t *testing.T) {
	for name, found := range map[string]bool{
		"America/New_York": true, "UTC": true, "Asia/Kolkata": true, "America": false, "../../etc/passwd": false,
		"/usr/share/zoneinfo/UTC": false, "Eastern Standard Time": false, "Nowhere/City": false, "Local": false,
		"america/new_york": false,
	} {
		if (FindZone(name) != nil) != found {
			t.Errorf("%s: want found=%v", name, found)
		}
	}
}

func TestBindNumbersOnlyWhatAStatementUses(t *testing.T) {
	sql, args := bind(`SELECT :b, :a, :b, x::date FROM t WHERE y = :missing`, map[string]any{"a": 1, "b": 2, "c": 3})
	if sql != `SELECT $1, $2, $1, x::date FROM t WHERE y = :missing` || len(args) != 2 || args[0] != 2 || args[1] != 1 {
		t.Fatal(sql, args)
	}
}
