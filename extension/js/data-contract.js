// Signed JSON contract shared by background verification and offline tests.
(function (root) {
  "use strict";
  const MAX_PAYLOAD = 16 * 1024 * 1024, MAX_ENVELOPE = 32 * 1024;
  const compatibility = { minimum_extension: "2.6.0", minimum_chrome: 120, minimum_firefox: 128 };
  const source = /^https:\/\/karakterer\.dtu\.dk\/Histogram\/[1-9][0-9]{0,3}\/([0-9A-Z]{5}(?:-[0-9]{1,3})?)\/(Summer|Winter)-([0-9]{4})$/;
  const resultFields = ["grade_source", "grade_period", "grades", "grading_scale", "grade_participants", "passpercent", "avg"];
  const courseFields = [...resultFields, "name", "name_en", "review_participants", "qualityscore", "workload", "lazyscore", "default_exam_id", "exam_history", "history_collected_at", "exam_default_note", "avgp", "pp"];
  const examFields = [...resultFields, "id", "year", "season", "classification", "distribution_status", "identity_status", "histogram_course", "title", "identity_note", "participant_difference"];
  const numericGrades = ["-3", "00", "02", "4", "7", "10", "12"];
  const binaryGrades = ["passed", "not_passed", "approved", "not_approved"];
  const gradeKeys = [...numericGrades, ...binaryGrades, "absent", "sick"];
  const own = (o, k) => Object.hasOwn(o, k);
  function assert(ok, message) { if (!ok) throw new Error(message); }
  function object(o) { return o !== null && typeof o === "object" && !Array.isArray(o); }
  function fields(o, allowed, required = []) {
    assert(object(o) && Object.keys(o).every(k => allowed.includes(k)) && required.every(k => own(o, k)), "Invalid schema fields");
  }
  function text(v, nullable = false) {
    assert((nullable && v === null) || (typeof v === "string" && [...v].length <= 4096 && !/[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/u.test(v)), "Invalid text");
  }
  function number(v, low, high, integer = false) {
    assert(typeof v === "number" && Number.isFinite(v) && v >= low && v <= high && (!integer || Number.isSafeInteger(v)), "Invalid numeric value");
  }
  function timestamp(v) {
    assert(typeof v === "string" && v.length <= 40 && /^\d{4}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:\d{2})$/.test(v) && Number.isFinite(Date.parse(v)), "Invalid timestamp");
    return Date.parse(v);
  }
  function parse(bytes, limit) {
    bytes = new Uint8Array(bytes);
    assert(bytes.byteLength <= limit, "JSON byte limit exceeded");
    const value = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
    // Scan only strings and structural punctuation before native parsing. Bound
    // nesting and reject duplicate/prototype keys without reserializing bytes.
    const stack = [];
    const tokens = /"(?:\\[\s\S]|[^"\\])*"|[{}\[\],:]/g;
    let match;
    while ((match = tokens.exec(value))) {
      const token = match[0], top = stack[stack.length - 1];
      if (token === "{" || token === "[") {
        stack.push({ object: token === "{", key: token === "{", keys: new Set() });
        assert(stack.length <= 16, "JSON nesting limit exceeded");
      } else if (token === "}" || token === "]") stack.pop();
      else if (token === "," && top && top.object) top.key = true;
      else if (token.startsWith('"') && top && top.object && top.key) {
        const key = JSON.parse(token);
        assert(!["__proto__", "prototype", "constructor"].includes(key) && !top.keys.has(key), "Duplicate or forbidden object key");
        top.keys.add(key); top.key = false;
      }
    }
    return JSON.parse(value);
  }
  function results(r) {
    assert(!own(r, "avgp") || own(r, "avg"), "Grade percentile without average");
    assert(!own(r, "pp") || own(r, "passpercent"), "Pass percentile without pass rate");
    for (const k of ["avgp", "pp", "qualityscore", "workload", "lazyscore", "passpercent"]) if (own(r, k)) number(r[k], 0, 100);
    for (const k of ["grade_participants", "review_participants"]) if (own(r, k)) number(r[k], 0, 1000000, true);
    if (own(r, "avg")) { number(r.avg, -3, 12); assert(r.grading_scale === "seven_point", "Invalid average scale"); }
    if (own(r, "grades")) {
      fields(r.grades, gradeKeys);
      assert(Object.keys(r.grades).length > 0, "Empty grades");
      for (let v of Object.values(r.grades)) {
        if (typeof v === "string") { assert(/^[0-9]{1,7}$/.test(v), "Invalid grade count"); v = Number(v); }
        number(v, 0, 1000000, true);
      }
      const numeric = numericGrades.some(k => Number(r.grades[k] || 0) > 0);
      const positive = binaryGrades.some(k => Number(r.grades[k] || 0) > 0);
      const scale = numeric && positive ? "mixed" : numeric ? "seven_point" : binaryGrades.some(k => own(r.grades, k)) ? "pass_fail" : "seven_point";
      assert(r.grading_scale === scale, "Inconsistent grading scale");
    }
  }
  function equal(a, b) {
    if (a === b) return true;
    return object(a) && object(b) && Object.keys(a).length === Object.keys(b).length &&
      Object.keys(a).every(k => own(b, k) && equal(a[k], b[k]));
  }
  function dataset(bytes, policy) {
    const data = parse(bytes, MAX_PAYLOAD);
    assert(object(data) && Object.keys(data).length > 0 && Object.keys(data).length <= 10000, "Invalid course count");
    for (const [id, course] of Object.entries(data)) {
      assert(/^[0-9A-Z]{5}$/.test(id), "Invalid course ID");
      fields(course, courseFields, ["default_exam_id", "exam_history", "history_collected_at"]);
      for (const k of ["name", "name_en", "exam_default_note"]) if (own(course, k)) text(course[k]);
      timestamp(course.history_collected_at); results(course);
      assert(Array.isArray(course.exam_history) && course.exam_history.length <= 128, "Invalid exam history");
      const exams = new Map();
      for (const exam of course.exam_history) {
        fields(exam, examFields, ["id", "grade_source", "grade_period", "year", "season", "classification", "distribution_status", "identity_status", "histogram_course"]);
        text(exam.id);
        const m = exam.id.match(source);
        assert(m && exam.grade_source === exam.id && !exams.has(exam.id), "Invalid source URL or duplicate exam");
        exams.set(exam.id, exam);
        assert(exam.histogram_course === m[1] && exam.season === m[2].toLowerCase() && exam.year === Number(m[3]) && exam.grade_period === m[2] + "-" + m[3], "Inconsistent exam identity");
        number(exam.year, 1900, 2200, true);
        assert(["ordinary_candidate", "resit_candidate", "undetermined"].includes(exam.classification), "Invalid classification");
        assert(["exact_course_id", "manually_approved_history", "different_course_requires_review", "variant_requires_review"].includes(exam.identity_status), "Invalid identity status");
        if (exam.identity_status === "exact_course_id") assert(m[1] === id, "Wrong course identity");
        if (exam.identity_status === "manually_approved_history") assert(own(policy.approved[id] || {}, m[1]), "Unapproved history");
        assert(!(policy.excluded[id] || []).includes(m[1]), "Excluded history");
        for (const k of ["title", "identity_note"]) if (own(exam, k)) text(exam[k], k === "title");
        results(exam);
        assert(["published", "suppressed"].includes(exam.distribution_status), "Invalid distribution");
        if (exam.distribution_status === "suppressed") {
          assert(!["grades", "avg", "passpercent", "grade_participants", "grading_scale", "participant_difference"].some(k => own(exam, k)), "Suppressed results must be absent");
        } else {
          assert(["grades", "grade_participants", "passpercent", "grading_scale"].every(k => own(exam, k)), "Missing published results");
          if (own(exam, "participant_difference")) {
            number(exam.participant_difference, -1000000, 1000000, true);
            assert(exam.grade_participants - Object.values(exam.grades).reduce((s, v) => s + Number(v), 0) === exam.participant_difference, "Inconsistent participant difference");
          }
        }
      }
      if (course.default_exam_id === null) assert(![...resultFields, "avgp", "pp"].some(k => own(course, k)), "Results without default");
      else {
        const selected = exams.get(course.default_exam_id);
        assert(selected && ["exact_course_id", "manually_approved_history"].includes(selected.identity_status) &&
          (selected.classification === "ordinary_candidate" || (policy.preferred[id] || []).includes(selected.histogram_course)), "Invalid default exam");
        for (const k of resultFields) assert(own(course, k) === own(selected, k) && equal(course[k], selected[k]), "Inconsistent default results");
      }
    }
    return data;
  }
  function base64(value) {
    assert(typeof value === "string" && /^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(value), "Invalid base64");
    return Uint8Array.from(atob(value), c => c.charCodeAt(0));
  }
  async function digest(bytes) {
    return Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)), b => b.toString(16).padStart(2, "0")).join("");
  }
  function origin(value) {
    assert(typeof value === "string" && /^https:\/\/[a-z0-9.-]+\/(?:[A-Za-z0-9_-]+\/)*$/.test(value), "Invalid update origin");
    return value;
  }
  async function envelope(bytes, config) {
    const e = parse(bytes, MAX_ENVELOPE);
    fields(e, ["key_id", "metadata", "signature"], ["key_id", "metadata", "signature"]);
    assert(typeof e.key_id === "string" && own(config.trusted_keys, e.key_id), "Unknown signing key");
    const raw = base64(e.metadata);
    const key = await crypto.subtle.importKey("spki", base64(config.trusted_keys[e.key_id]), { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" }, false, ["verify"]);
    assert(key.algorithm.modulusLength === 3072 && Array.from(key.algorithm.publicExponent).join(",") === "1,0,1", "Invalid RSA public key");
    assert(await crypto.subtle.verify("RSASSA-PKCS1-v1_5", key, base64(e.signature), raw), "Invalid release signature");
    const m = parse(raw, MAX_ENVELOPE);
    const keys = ["contract_version", "schema_version", "dataset", "path", "sequence", "published_at", "collected_at", "byte_length", "sha256", "compatibility", "key_id", "origin", "channel", "evidence_sha256", "promotion_commit", "request_id"];
    fields(m, keys, keys);
    assert(m.contract_version === 1 && m.schema_version === 1 && m.dataset === "dtu-course-data", "Unsupported data contract");
    assert(m.key_id === e.key_id && m.origin === origin(config.origin) && m.channel === config.channel, "Wrong release trust domain");
    assert(equal(m.compatibility, compatibility), "Unsupported compatibility requirements");
    if (config.clientVersion !== undefined) {
      assert(typeof config.clientVersion === "string" && /^\d+(?:\.\d+){0,3}$/.test(config.clientVersion), "Invalid installed extension version");
      const actual = config.clientVersion.split(".").map(Number), required = compatibility.minimum_extension.split(".").map(Number);
      let comparison = 0;
      for (let i = 0; i < 4 && comparison === 0; i++) comparison = (actual[i] || 0) - (required[i] || 0);
      assert(comparison >= 0, "Installed extension does not support this release");
    }
    number(m.sequence, 1, Number.MAX_SAFE_INTEGER, true);
    number(m.byte_length, 1, MAX_PAYLOAD, true);
    for (const k of ["sha256", "evidence_sha256"]) assert(typeof m[k] === "string" && /^[0-9a-f]{64}$/.test(m[k]), "Invalid digest");
    assert(typeof m.promotion_commit === "string" && typeof m.request_id === "string" && /^[0-9a-f]{40}$/.test(m.promotion_commit) && /^[a-z0-9][a-z0-9-]{0,63}$/.test(m.request_id), "Invalid release identity");
    assert(m.path === "releases/" + m.sequence + "-" + m.sha256 + "/data.json", "Invalid payload path");
    assert(timestamp(m.collected_at) <= timestamp(m.published_at) && timestamp(m.published_at) <= Date.now() + 300000, "Invalid release chronology");
    return m;
  }
  async function payload(bytes, metadata, policy) {
    assert(bytes.byteLength === metadata.byte_length && await digest(bytes) === metadata.sha256, "Payload digest or length mismatch");
    return dataset(bytes, policy);
  }
  async function download(url, limit, fetcher = fetch, signal) {
    const controller = new AbortController();
    const abort = () => controller.abort();
    if (signal) { signal.addEventListener("abort", abort); if (signal.aborted) abort(); }
    const timer = setTimeout(() => controller.abort(), 30000);
    let reader;
    try {
      const response = await fetcher(url, { credentials: "omit", referrerPolicy: "no-referrer", redirect: "error", cache: "no-cache", signal: controller.signal });
      assert(response.ok && response.status === 200 && !response.redirected && response.url === url, "Unexpected download response");
      assert(response.body, "Missing response stream");
      reader = response.body.getReader();
      const chunks = []; let length = 0;
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        length += value.byteLength;
        assert(length <= limit, "Download byte limit exceeded");
        chunks.push(value);
      }
      const bytes = new Uint8Array(length); let offset = 0;
      for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length; }
      return bytes;
    } finally {
      clearTimeout(timer);
      if (signal) signal.removeEventListener("abort", abort);
      if (reader) await reader.cancel().catch(() => {});
    }
  }
  const api = { MAX_PAYLOAD, MAX_ENVELOPE, assert, dataset, envelope, payload, digest, download, parse, origin };
  root.DTURelease = api;
  if (typeof module !== "undefined") module.exports = api;
})(globalThis);
