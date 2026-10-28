import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import EChart from "@/components/charts/EChart";

// echarts needs a real canvas, so render a plain div that exposes its props
vi.mock("echarts-for-react", () => ({
  default: ({
    style,
    className,
  }: {
    style?: React.CSSProperties;
    className?: string;
  }) => <div data-testid="echart" style={style} className={className} />,
}));

describe("EChart", () => {
  it("puts size classes on the wrapper, not on the chart div", () => {
    render(<EChart option={{}} className="h-96 w-full" />);
    const chart = screen.getByTestId("echart");

    expect(chart.parentElement).toHaveClass("h-96", "w-full");
    expect(chart).not.toHaveClass("h-96");
  });

  it("makes the chart fill the wrapper", () => {
    render(<EChart option={{}} className="h-96" />);
    const chart = screen.getByTestId("echart");

    expect(chart).toHaveStyle({ height: "100%", width: "100%" });
  });
});
