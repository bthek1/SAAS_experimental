import { describe, expect, it } from "vitest";
import { isPublicPath } from "./publicPaths";

describe("isPublicPath", () => {
  it.each(["/", "/login", "/signup", "/take/abc", "/take-battery/abc"])(
    "%s renders without the shell",
    (path) => expect(isPublicPath(path)).toBe(true),
  );

  it.each(["/dashboard", "/questionnaires", "/take", "/loginx"])(
    "%s renders inside the shell",
    (path) => expect(isPublicPath(path)).toBe(false),
  );
});
