import { useEffect, useRef } from "react";
import * as d3 from "d3";

// Root family tree. The root is the trunk (left); each lemma is a branch (right).
// Branch thickness grows with how often the form occurs. Click a branch to drill down.
// D3 draws the SVG; React only supplies data and the selected lemma.
export default function TreeView({ tree, selectedLemma, onSelectForm }) {
  const ref = useRef(null);

  useEffect(() => {
    const svg = d3.select(ref.current);
    svg.selectAll("*").remove();
    if (!tree) return;

    const rowH = 46;
    const width = 480;
    const margin = { top: 16, right: 170, bottom: 16, left: 80 };
    const innerH = Math.max(100, tree.forms.length * rowH);
    const height = innerH + margin.top + margin.bottom;
    svg.attr("viewBox", `0 0 ${width} ${height}`);

    const data = {
      name: tree.root,
      children: tree.forms.map((f) => ({ name: f.lemma, count: f.count })),
    };
    const hier = d3.hierarchy(data);
    d3.tree().size([innerH, width - margin.left - margin.right])(hier);

    const g = svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);

    g.selectAll("path")
      .data(hier.links())
      .join("path")
      .attr("fill", "none")
      .attr("stroke", "var(--branch)")
      .attr("stroke-linecap", "round")
      .attr("stroke-width", (d) => 1.5 + d.target.data.count * 1.5)
      .attr("d", d3.linkHorizontal().x((d) => d.y).y((d) => d.x));

    const node = g
      .selectAll("g.node")
      .data(hier.descendants())
      .join("g")
      .attr("class", (d) =>
        "node" + (d.depth ? " leaf" : "") + (d.depth && d.data.name === selectedLemma ? " selected" : "")
      )
      .attr("transform", (d) => `translate(${d.y},${d.x})`)
      .style("cursor", (d) => (d.depth ? "pointer" : "default"))
      .on("click", (_e, d) => d.depth && onSelectForm(d.data.name));

    // A generous invisible row behind each branch label: easier to hit, and lights up on hover.
    node
      .filter((d) => d.depth)
      .append("rect")
      .attr("class", "hit")
      .attr("x", -16)
      .attr("y", -19)
      .attr("width", 196)
      .attr("height", 38)
      .attr("rx", 8);

    node.append("circle").attr("r", (d) => (d.depth ? 6 : 9));

    node
      .append("text")
      .attr("dy", "0.32em")
      .attr("x", (d) => (d.depth ? 12 : -14))
      .attr("text-anchor", (d) => (d.depth ? "start" : "end"))
      .attr("font-family", "'Amiri Quran', serif")
      .attr("font-size", (d) => (d.depth ? 20 : 26))
      .text((d) => d.data.name);

    node
      .filter((d) => d.depth)
      .append("text")
      .attr("class", "count")
      .attr("dy", "0.32em")
      .attr("x", 112)
      .attr("font-size", 13)
      .text((d) => `x${d.data.count}`);
  }, [tree, selectedLemma, onSelectForm]);

  return <svg ref={ref} className="tree-svg" role="img" aria-label="Root family tree" />;
}
