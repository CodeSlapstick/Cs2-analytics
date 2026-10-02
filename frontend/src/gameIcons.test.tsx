import { describe, expect, it } from "vitest";
import { weaponIconFor } from "./gameIcons";

describe("game icon mapping", () => {
  it("maps parser aliases without guessing unknown equipment", () => {
    expect(weaponIconFor("AK-47")).not.toBeNull();
    expect(weaponIconFor("weapon_m4a1_silencer")).not.toBeNull();
    expect(weaponIconFor("USP-S")).not.toBeNull();
    expect(weaponIconFor("Incendiary Grenade")).not.toBeNull();
    expect(weaponIconFor("future_unknown_weapon")).toBeNull();
    expect(weaponIconFor(null)).toBeNull();
  });
});
