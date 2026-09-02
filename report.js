/* TM Watch — free instant-report client logic (c66).
 *
 * Pure logic lives in this UMD module so selftest_site.py can drive it via
 * quickjs against Python ground truth (VM has no Node; PAT lacks workflow
 * scope — quickjs parity gate is the binding CI substitute).
 *
 * Sharding contract MIRRORS gen_index.py shard_chars(): one shard per
 * distinct phonetic-first-char of the query's distinctive tokens (fallback:
 * all tokens; empty phon code -> token first char; non-alnum -> "_").
 *
 * Browser side (index.html) supplies fetchShard(ch) -> Promise<rows|null>.
 * NOT legal advice: a flag means "a human should look".
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory(require("./matcher.js"));
  else root.tmReport = factory(root.tmMatcher);
})(typeof self !== "undefined" ? self : this, function (M) {
  "use strict";

  function shardChars(text) {
    var norm = M.normalize(text);
    var toks = norm.split(" ").filter(function (t) { return t; });
    var dis = toks.filter(function (t) { return !isStopword(t); });
    if (dis.length === 0) dis = toks;
    var set = {};
    for (var i = 0; i < dis.length; i++) {
      var code = M.metaphoneLite(dis[i]);
      var ch = (code || dis[i] || "_").charAt(0);
      if (!/[A-Z0-9]/.test(ch)) ch = "_";
      set[ch] = true;
    }
    var out = Object.keys(set).sort();
    return out.length ? out : ["_"];
  }

  // Duplicated from matcher.js internals (STOPWORDS is not exported; keep in
  // sync — selftest_site.py cross-checks shardChars against Python, which
  // catches drift here).
  var STOP = ["THE","AND","OF","FOR","A","AN","BY","CO","INC","LLC","LLP",
    "CORP","LTD","USA","GROUP","SYSTEMS","SYSTEM","SOLUTIONS","SERVICES",
    "SERVICE","TECHNOLOGIES","TECHNOLOGY","TECH","GLOBAL","INTERNATIONAL",
    "BRANDS","BRAND","COMPANY","PRODUCTS","PRODUCT","LABS","LAB","STUDIO",
    "STUDIOS","ONLINE","SHOP","STORE"];
  function isStopword(t) { return STOP.indexOf(t) !== -1; }

  /* rows: array of [serial, mark, date, classes, phon, squeezed, event?]
   * date = gazette publication date (event "P" published for opposition,
   * "R" registered) on the TMOG path; filing date on the legacy path.
   * (already deduped by serial by the caller). Returns flagged matches,
   * strongest first. */
  function runReport(query, rows) {
    var out = [];
    for (var i = 0; i < rows.length; i++) {
      var r = rows[i];
      var res = M.compare(query, r[1]);
      if (res.flag) {
        out.push({ serial: r[0], mark: r[1], filed: r[2], classes: r[3],
                   event: r[6] || "", reasons: res.reasons,
                   editSim: res.detail.edit_sim });
      }
    }
    out.sort(function (a, b) {
      return (b.reasons.length - a.reasons.length) || (b.editSim - a.editSim) ||
             (a.serial - b.serial);
    });
    return out;
  }

  /* Full pipeline given an async shard fetcher; dedupes rows across shards. */
  function report(query, fetchShard) {
    var chars = shardChars(query);
    return Promise.all(chars.map(function (ch) { return fetchShard(ch); }))
      .then(function (shards) {
        var seen = {}, rows = [];
        for (var i = 0; i < shards.length; i++) {
          var s = shards[i] || [];
          for (var j = 0; j < s.length; j++) {
            if (!seen[s[j][0]]) { seen[s[j][0]] = true; rows.push(s[j]); }
          }
        }
        return { query: query, shards: chars, scanned: rows.length,
                 matches: runReport(query, rows) };
      });
  }

  return { shardChars: shardChars, runReport: runReport, report: report };
});
