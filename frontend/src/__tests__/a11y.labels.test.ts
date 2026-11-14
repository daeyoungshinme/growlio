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
    if (ts.isJsxSelfClosingElement(node) && node.tagName.getText() === "label") {
      const { line } = sf.getLineAndCharacterOfPosition(node.getStart());
      found.push(`${relative(SRC, file)}:${line + 1}`);
    }
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

/** 속성 값의 비교용 텍스트 — 조건식이면 두 갈래를 각각(원화↔달러처럼 보이는 쪽 id를 고르는 경우). */
function attrValueTexts(init: ts.JsxAttributeValue | undefined): string[] {
  if (!init) return [];
  if (ts.isStringLiteral(init)) return [JSON.stringify(init.text)];
  if (ts.isJsxExpression(init) && init.expression) return exprTexts(init.expression);
  return [];
}

function exprTexts(expr: ts.Expression): string[] {
  if (ts.isParenthesizedExpression(expr)) return exprTexts(expr.expression);
  if (ts.isConditionalExpression(expr))
    return [...exprTexts(expr.whenTrue), ...exprTexts(expr.whenFalse)];
  if (ts.isStringLiteral(expr) || ts.isNoSubstitutionTemplateLiteral(expr))
    return [JSON.stringify(expr.text)];
  // 조건부로 속성을 빼는 갈래(`cond ? id : undefined`)는 가리키는 값이 아니다
  if (
    expr.kind === ts.SyntaxKind.NullKeyword ||
    (ts.isIdentifier(expr) && expr.text === "undefined")
  )
    return [];
  return [expr.getText()];
}

/**
 * htmlFor·aria-labelledby가 가리키는 값이 같은 파일 어딘가의 `id` 속성(요소든 컴포넌트 prop이든)으로 쓰이는지.
 * 렌더 조건까지는 못 보지만, 존재하지 않는 id나 오타는 잡는다(plans/132 D2).
 */
function danglingReferences(file: string): string[] {
  const sf = ts.createSourceFile(
    file,
    readFileSync(file, "utf8"),
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TSX,
  );
  const ids = new Set<string>();
  const refs: { text: string; pos: number }[] = [];
  const visit = (node: ts.Node) => {
    if (ts.isJsxAttribute(node)) {
      const name = node.name.getText();
      if (name === "id") attrValueTexts(node.initializer).forEach((t) => ids.add(t));
      if (name === "htmlFor" || name === "aria-labelledby") {
        attrValueTexts(node.initializer).forEach((text) =>
          refs.push({ text, pos: node.getStart() }),
        );
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(sf);
  return refs
    .filter((r) => !ids.has(r.text))
    .map(
      (r) => `${relative(SRC, file)}:${sf.getLineAndCharacterOfPosition(r.pos).line + 1} ${r.text}`,
    );
}

describe("label 접근성", () => {
  it("모든 label이 htmlFor를 갖거나 네이티브 컨트롤을 감싼다", () => {
    const offenders = collectTsx(SRC).flatMap(unassociatedLabels);
    expect(offenders).toEqual([]);
  });

  it("htmlFor·aria-labelledby가 같은 파일의 id를 가리킨다", () => {
    const offenders = collectTsx(SRC).flatMap(danglingReferences);
    expect(offenders).toEqual([]);
  });
});
