// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { LangProvider } from "./i18n";
import { readReviewNotes, ReviewNotes } from "./ReviewNotes";

describe("review notes", () => {
  afterEach(cleanup);

  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("saves a timed note and seeks to its moment", async () => {
    const user = userEvent.setup();
    const onSeek = vi.fn();
    render(<LangProvider><ReviewNotes demo="match.dem" round={7} playbackTime={24.36} onSeek={onSeek} /></LangProvider>);

    await user.type(screen.getByLabelText("เขียนโน้ตสำหรับรอบนี้"), "CT ไม่มีคนช่วยจาก connector");
    await user.click(screen.getByRole("button", { name: "เพิ่มโน้ต" }));

    expect(screen.getByText("CT ไม่มีคนช่วยจาก connector")).toBeTruthy();
    expect(readReviewNotes("match.dem", 7)).toMatchObject([{ time: 24.4, text: "CT ไม่มีคนช่วยจาก connector" }]);
    await user.click(screen.getByRole("button", { name: "0:24" }));
    expect(onSeek).toHaveBeenCalledWith(24.4);
  });

  it("keeps rounds separate and edits an existing note", async () => {
    const user = userEvent.setup();
    const { rerender } = render(
      <LangProvider><ReviewNotes demo="match.dem" round={1} playbackTime={null} onSeek={vi.fn()} /></LangProvider>,
    );
    await user.type(screen.getByLabelText("เขียนโน้ตสำหรับรอบนี้"), "โน้ตเดิม");
    await user.click(screen.getByRole("button", { name: "เพิ่มโน้ต" }));
    await user.click(screen.getByRole("button", { name: "แก้ไข" }));
    const edit = screen.getByLabelText("แก้ไขโน้ต");
    await user.clear(edit);
    await user.type(edit, "โน้ตที่แก้แล้ว");
    await user.click(screen.getByRole("button", { name: "บันทึก" }));
    expect(readReviewNotes("match.dem", 1)[0].text).toBe("โน้ตที่แก้แล้ว");

    rerender(<LangProvider><ReviewNotes demo="match.dem" round={2} playbackTime={null} onSeek={vi.fn()} /></LangProvider>);
    expect(screen.getByText("ยังไม่มีโน้ตในรอบนี้")).toBeTruthy();
  });
});
