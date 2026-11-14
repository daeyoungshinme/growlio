// @vitest-environment node
/**
 * 모든 <label>이 컨트롤과 연결돼 있는지 정적 검사한다(plans/131).
 * htmlFor가 있거나 input·select·textarea를 감싸야 한다 — 여러 입력을 묶는 제목은 label 대신
 * <p id> + role="group" aria-labelledby, 읽기 전용 표시는 <p>로.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import ts from "typescript";
import { describe, expect, it } from "vitest";

const SRC = join(__dirname, "..");
const NATIVE_CONTROLS = new Set(["input", "select", "textarea"]);

function collectTsx(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) {
      if (name !== "__tests__" && name !== "test") collectTsx(p, out);
    } else if (p.endsWith(".tsx") && !p.includes(".test.")) {
      out.push(p);
    }
  }
  return out;
}

function unassociatedLabels(file: string): string[] {
  const sf = ts.createSourceFile(
    file,
    readFileSync(file, "utf8"),
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TSX,
  );
  const found: string[] = [];
  const visit = (node: ts.Node) => {
    if (ts.isJsxElement(node) && node.openingElement.tagName.getText() === "label") {
      const hasFor = node.openingElement.attributes.properties.some(
        (a) => ts.isJsxAttribute(a) && a.name.getText() === "htmlFor",
      );
      let wrapsControl = false;
      const walk = (n: ts.Node) => {
        if (
          (ts.isJsxOpeningElement(n) || ts.isJsxSelfClosingElement(n)) &&
          NATIVE_CONTROLS.has(n.tagName.getText())
        ) {
          wrapsControl = true;
        }
        ts.forEachChild(n, walk);
      };
      walk(node);
      if (!hasFor && !wrapsControl) {
        const { line } = sf.getLineAndCharacterOfPosition(node.getStart());
        found.push(`${relative(SRC, file)}:${line + 1}`);
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(sf);
  return found;
}

describe("label 접근성", () => {
  it("모든 label이 htmlFor를 갖거나 네이티브 컨트롤을 감싼다", () => {
    const offenders = collectTsx(SRC).flatMap(unassociatedLabels);
    expect(offenders).toEqual([]);
  });
});
