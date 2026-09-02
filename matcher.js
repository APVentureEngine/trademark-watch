/* TM Watch matcher v2 — JS port of matcher.py (deterministic trademark-name
 * similarity flagging). MUST mirror matcher.py exactly; parity is enforced by
 * selftest.js against parity-vectors.json (generated from the Python side).
 * Contract: identical flag + reason kinds + phonetic codes + normalized forms.
 * Float FORMATTING inside reason strings may differ (Python %.2f vs toFixed);
 * the comparisons themselves are raw IEEE doubles and identical.
 *
 * UMD-lite: works as a Node require() and as a browser <script> (window.tmMatcher).
 * Rule 6 (rare-token, v2/c76) needs the common-token set: call
 * tmMatcher.setCommonTokens(arrayFromCommonTokensJson) first; until then the
 * rule is OFF and compare() behaves exactly like v1 (same as Python without
 * common-tokens.json).
 * NOT legal advice: a flag means "a human should look".
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.tmMatcher = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  var STOPWORDS = new Set([
    "THE", "AND", "OF", "FOR", "A", "AN", "BY", "CO", "INC", "LLC", "LLP",
    "CORP", "LTD", "USA", "GROUP", "SYSTEMS", "SYSTEM", "SOLUTIONS",
    "SERVICES", "SERVICE", "TECHNOLOGIES", "TECHNOLOGY", "TECH", "GLOBAL",
    "INTERNATIONAL", "BRANDS", "BRAND", "COMPANY", "PRODUCTS", "PRODUCT",
    "LABS", "LAB", "STUDIO", "STUDIOS", "ONLINE", "SHOP", "STORE",
  ]);

  function normalize(s) {
    s = s.toUpperCase();
    s = s.split("&").join(" AND ").split("+").join(" PLUS ");
    s = s.replace(/['’]/g, "");            // apostrophes vanish
    s = s.replace(/[^A-Z0-9]+/g, " ");          // hyphens/dots/etc -> space
    return s.replace(/\s+/g, " ").trim();
  }

  function squeeze(s) { return s.split(" ").join(""); }

  function dedouble(s) {
    var out = "";
    for (var i = 0; i < s.length; i++) {
      if (out.length === 0 || out[out.length - 1] !== s[i]) out += s[i];
    }
    return out;
  }

  // Damerau-Levenshtein (optimal string alignment), same DP as matcher.py
  function dlDistance(a, b) {
    var la = a.length, lb = b.length;
    if (la === 0) return lb;
    if (lb === 0) return la;
    var d = [];
    for (var i = 0; i <= la; i++) { d.push(new Array(lb + 1).fill(0)); d[i][0] = i; }
    for (var j = 0; j <= lb; j++) d[0][j] = j;
    for (i = 1; i <= la; i++) {
      for (j = 1; j <= lb; j++) {
        var cost = a[i - 1] === b[j - 1] ? 0 : 1;
        d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost);
        if (i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) {
          d[i][j] = Math.min(d[i][j], d[i - 2][j - 2] + 1);
        }
      }
    }
    return d[la][lb];
  }

  function dlSimilarity(a, b) {
    if (a.length === 0 && b.length === 0) return 1.0;
    var m = Math.max(a.length, b.length);
    return m ? 1.0 - dlDistance(a, b) / m : 0.0;
  }

  var VOWELS = "AEIOUY";

  function metaphoneLite(s) {
    s = squeeze(s);
    if (!s) return "";
    // digraphs first — SAME order as matcher.py
    s = s.split("PH").join("F").split("GH").join("K").split("CK").join("K");
    s = s.split("SCH").join("SK").split("SH").join("X").split("CH").join("X");
    s = s.split("TH").join("T").split("WH").join("W");
    var out = "";
    for (var i = 0; i < s.length; i++) {
      var ch = s[i];
      if (ch >= "0" && ch <= "9") { out += ch; continue; }
      if (VOWELS.indexOf(ch) !== -1) {
        if (i === 0) out += "A";      // initial vowel kept as A
        continue;                     // non-initial vowels dropped
      }
      // terminal-lookahead guard (c64 bug): nxt must be non-empty
      var nxt = i + 1 < s.length ? s[i + 1] : "";
      if (ch === "C") out += (nxt && "EIY".indexOf(nxt) !== -1) ? "S" : "K";
      else if (ch === "G") out += (nxt && "EIY".indexOf(nxt) !== -1) ? "J" : "K";
      else if (ch === "Q") out += "K";
      else if (ch === "Z") out += "S";
      else if (ch === "V") out += "F";
      else if (ch === "X") out += "KS";
      else if (ch === "W" || ch === "H") continue;
      else out += ch;
    }
    return dedouble(out);
  }

  function stripPlural(tok) {
    if (tok.length > 3 && tok.slice(-1) === "S" && tok.slice(-2) !== "SS") {
      return tok.slice(0, -1);
    }
    return tok;
  }

  function tokens(norm) { return norm.split(" ").filter(function (t) { return t; }); }

  function distinctive(toks) {
    return toks.filter(function (t) { return !STOPWORDS.has(t); });
  }

  var COMMON = null;            // Set of common tokens, or null = rule 6 off
  var RARE_MIN_LEN = 4;
  function setCommonTokens(list) { COMMON = list ? new Set(list) : null; }
  function isRare(tok) {
    return COMMON !== null && tok.length >= RARE_MIN_LEN && !COMMON.has(tok);
  }

  var TOKEN_PHON_MIN_SIM = 0.60;

  function tokenMatch(t1, t2) {
    if (t1 === t2) return true;
    if (stripPlural(t1) === stripPlural(t2)) return true;
    if (t1.length >= 3 && t2.length >= 3) {
      var c1 = metaphoneLite(t1), c2 = metaphoneLite(t2);
      // v2.1: 1-2 char codes only count when the tokens are within one edit
      // v2.2: 3+ char codes also need the tokens themselves >= 60% similar
      if (c1 === c2) {
        if (dlDistance(t1, t2) <= 1) return true;
        if (c1.length >= 3 && dlSimilarity(t1, t2) >= TOKEN_PHON_MIN_SIM) return true;
      }
    }
    return false;
  }

  function compare(name1, name2) {
    var n1 = normalize(name1), n2 = normalize(name2);
    var s1 = squeeze(n1), s2 = squeeze(n2);
    var reasons = [];

    // 1. identical after normalization
    if (s1 && s1 === s2) reasons.push("identical");

    // 2. containment
    var d1 = dedouble(s1), d2 = dedouble(s2);
    var small = d1.length <= d2.length ? d1 : d2;
    var big = d1.length <= d2.length ? d2 : d1;
    if (small.length >= 5 && big.indexOf(small) !== -1 && small !== big) {
      reasons.push("containment");
    } else {
      // whole-mark-as-token: entire shorter mark appears as a token
      var toks1 = tokens(n1), toks2 = tokens(n2);
      if (s1.length <= s2.length && toks1.length === 1 && toks2.indexOf(s1) !== -1) {
        reasons.push("whole-mark-token");
      } else if (s2.length < s1.length && toks2.length === 1 && toks1.indexOf(s2) !== -1) {
        reasons.push("whole-mark-token");
      }
    }

    // 3. edit distance on squeezed strings
    var sim = dlSimilarity(s1, s2);
    var dist = dlDistance(s1, s2);
    if (s1 && s2) {
      if (Math.max(s1.length, s2.length) <= 4 && dist <= 1) {
        reasons.push("edit-short(dist=" + dist + ")");
      } else if (sim >= 0.80) {
        reasons.push("edit(sim=" + sim.toFixed(2) + ")");
      }
    }

    // 4. phonetic
    var p1 = metaphoneLite(n1), p2 = metaphoneLite(n2);
    if (p1 && p2 && Math.min(p1.length, p2.length) >= 2) {
      var pdist = dlDistance(p1, p2);
      if (p1 === p2) reasons.push("phonetic-equal(" + p1 + ")");
      else if (pdist === 1 && sim >= 0.45) {
        reasons.push("phonetic-near(" + p1 + "~" + p2 + ",sim=" + sim.toFixed(2) + ")");
      }
    }

    // 5. token overlap
    var t1 = distinctive(tokens(n1));
    var t2 = distinctive(tokens(n2));
    if (t1.length && t2.length && (t1.length > 1 || t2.length > 1)) {
      var smaller = t1.length <= t2.length ? t1 : t2;
      var larger = t1.length <= t2.length ? t2 : t1;
      var matched = 0;
      for (var k = 0; k < smaller.length; k++) {
        for (var m = 0; m < larger.length; m++) {
          if (tokenMatch(smaller[k], larger[m])) { matched++; break; }
        }
      }
      var ratio = matched / smaller.length;
      if (matched >= 1 && ratio >= 0.67) {
        reasons.push("tokens(" + matched + "/" + smaller.length + ")");
      }

      // 6. rare shared token (v2): exact/plural-stripped share; v2.2 adds one-edit phonetic-equal rare variants
      var rare = null;
      for (var x = 0; x < smaller.length && rare === null; x++) {
        var sa = stripPlural(smaller[x]);
        if (!isRare(sa)) continue;
        for (var y = 0; y < larger.length; y++) {
          var sb = stripPlural(larger[y]);
          if (sb === sa) { rare = sa; break; }
          // v2.2: rare near-variant (both rare, same code >=3 chars, one edit)
          if (isRare(sb) && dlDistance(sa, sb) <= 1) {
            var ca = metaphoneLite(sa);
            if (ca.length >= 3 && ca === metaphoneLite(sb)) { rare = sa + "~" + sb; break; }
          }
        }
      }
      if (rare !== null) reasons.push("rare-token(" + rare + ")");
    }

    var detail = { norm1: n1, norm2: n2, phon1: p1, phon2: p2,
                   edit_sim: Math.round(sim * 1000) / 1000 };
    return { flag: reasons.length > 0, reasons: reasons, detail: detail };
  }

  return {
    normalize: normalize, squeeze: squeeze, dedouble: dedouble,
    dlDistance: dlDistance, dlSimilarity: dlSimilarity,
    metaphoneLite: metaphoneLite, compare: compare,
    setCommonTokens: setCommonTokens, isRare: isRare,
  };
});
