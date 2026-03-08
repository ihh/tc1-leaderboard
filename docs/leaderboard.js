(function () {
  "use strict";

  const SCORE_COMPONENTS = [
    { key: "diversity", label: "Diversity" },
    { key: "annotation", label: "Annotation" },
    { key: "functionality", label: "Functionality" },
    { key: "size", label: "Size" },
  ];

  async function fetchJSON(url) {
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`${resp.status} ${resp.statusText}`);
    return resp.json();
  }

  function scoreBar(value, max) {
    const pct = Math.min(100, (value / max) * 100);
    return `<span class="score-bar"><span class="score-bar-fill" style="width:${pct}%"></span></span>`;
  }

  function statusIcon(status) {
    const cls = "status-" + status;
    const sym = status === "pass" ? "\u2713" : status === "warn" ? "\u26A0" : "\u2717";
    return `<span class="${cls}">${sym}</span>`;
  }

  function buildRow(entry, rank) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td class="rank">${rank}</td>
      <td class="team"><a data-team="${entry.team}">${entry.team}</a></td>
      <td class="score-total">${scoreBar(entry.score, 100)}${entry.score.toFixed(1)}</td>
      <td class="score-sub hide-mobile">${(entry.scores?.diversity ?? "").toString().slice(0, 4)}</td>
      <td class="score-sub hide-mobile">${(entry.scores?.annotation ?? "").toString().slice(0, 4)}</td>
      <td class="score-sub hide-mobile">${(entry.scores?.functionality ?? "").toString().slice(0, 4)}</td>
      <td class="score-sub hide-mobile">${(entry.scores?.size ?? "").toString().slice(0, 4)}</td>
      <td class="count">${entry.n_sequences}</td>
      <td class="count">${entry.n_families}</td>
      <td class="score-sub"><code>${(entry.commit || "").slice(0, 7)}</code></td>
    `;
    return tr;
  }

  // Residue coloring by physicochemical property
  const AA_CLASSES = {};
  "AILMFWV".split("").forEach(c => AA_CLASSES[c] = "aa-hydrophobic");
  "KR".split("").forEach(c => AA_CLASSES[c] = "aa-positive");
  "DE".split("").forEach(c => AA_CLASSES[c] = "aa-negative");
  "NQST".split("").forEach(c => AA_CLASSES[c] = "aa-polar");
  "C".split("").forEach(c => AA_CLASSES[c] = "aa-cysteine");
  "G".split("").forEach(c => AA_CLASSES[c] = "aa-glycine");
  "P".split("").forEach(c => AA_CLASSES[c] = "aa-proline");
  "HY".split("").forEach(c => AA_CLASSES[c] = "aa-aromatic");

  function renderAlignment(alignment) {
    if (!alignment || !alignment.sequences) return "";

    const ids = Object.keys(alignment.sequences);
    const seqs = Object.values(alignment.sequences);
    const triad = alignment.catalytic_triad || "";
    const len = seqs[0].length;
    const BLOCK = 80;
    const pad = Math.max(...ids.map(s => s.length));

    let html = '<div class="alignment"><h3>Protein alignment</h3>';
    html += '<div class="aln-legend">';
    html += '<span class="aa-hydrophobic">hydrophobic</span> ';
    html += '<span class="aa-positive">positive</span> ';
    html += '<span class="aa-negative">negative</span> ';
    html += '<span class="aa-polar">polar</span> ';
    html += '<span class="aa-cysteine">cysteine</span> ';
    html += '<span class="aa-glycine">glycine</span> ';
    html += '<span class="aa-aromatic">aromatic</span> ';
    html += '<span class="aa-triad">triad</span>';
    html += '</div><pre class="aln-block">';

    for (let start = 0; start < len; start += BLOCK) {
      const end = Math.min(start + BLOCK, len);

      // Sequence rows
      for (let s = 0; s < ids.length; s++) {
        const label = ids[s].padEnd(pad + 2);
        let row = `<span class="aln-label">${label}</span>`;
        for (let i = start; i < end; i++) {
          const aa = seqs[s][i];
          const isTriad = triad[i] && "DdE".includes(triad[i]);
          const cls = isTriad ? "aa-triad" : (AA_CLASSES[aa] || "");
          row += cls ? `<span class="${cls}">${aa}</span>` : aa;
        }
        html += row + "\n";
      }

      // Triad annotation row
      let triadRow = " ".repeat(pad + 2);
      for (let i = start; i < end; i++) {
        const ch = triad[i] || ".";
        if ("DdE".includes(ch)) {
          triadRow += `<span class="aa-triad">${ch}</span>`;
        } else {
          triadRow += " ";
        }
      }
      html += triadRow + "\n";

      // Conservation row
      let consRow = " ".repeat(pad + 2);
      for (let i = start; i < end; i++) {
        const col = seqs.map(s => s[i]);
        const unique = new Set(col);
        if (unique.size === 1) consRow += "*";
        else if (col.every(r => "AILMFWV".includes(r))) consRow += ":";
        else if (col.every(r => "DE".includes(r))) consRow += ":";
        else if (col.every(r => "KR".includes(r))) consRow += ":";
        else if (col.every(r => "NQST".includes(r))) consRow += ":";
        else consRow += " ";
      }
      html += consRow + "\n\n";
    }

    html += "</pre></div>";
    return html;
  }

  function buildDetailRow(teamData) {
    const tr = document.createElement("tr");
    tr.className = "detail-row";
    const td = document.createElement("td");
    td.colSpan = 10;

    let checksHTML = "";
    if (teamData.checks) {
      checksHTML = '<h3>Validation checks</h3><ul class="check-list">';
      for (const [name, info] of Object.entries(teamData.checks)) {
        checksHTML += `<li>${statusIcon(info.status)} <strong>${name}</strong>`;
        if (info.messages && info.messages.length) {
          checksHTML += `: ${info.messages.join("; ")}`;
        }
        checksHTML += "</li>";
      }
      checksHTML += "</ul>";
    }

    let issuesHTML = "";
    if (teamData.per_sequence_issues) {
      const withIssues = Object.entries(teamData.per_sequence_issues).filter(
        ([, v]) => v.length > 0
      );
      if (withIssues.length) {
        issuesHTML = "<h3>Per-sequence issues</h3><ul class='issue-list'>";
        for (const [seqId, issues] of withIssues) {
          issuesHTML += `<li><strong>${seqId}</strong>: ${issues.join("; ")}</li>`;
        }
        issuesHTML += "</ul>";
      }
    }

    const alignmentHTML = renderAlignment(teamData.alignment);

    td.innerHTML = `<div class="detail-panel">${checksHTML}${issuesHTML}${alignmentHTML}</div>`;
    tr.appendChild(td);
    tr.style.display = "none";
    return tr;
  }

  async function init() {
    const tbody = document.getElementById("leaderboard-body");
    const updatedEl = document.getElementById("updated");

    let data;
    try {
      data = await fetchJSON("leaderboard.json");
    } catch (e) {
      tbody.innerHTML =
        '<tr><td colspan="10" class="empty-state">No leaderboard data yet. Submit an entry to get started.</td></tr>';
      return;
    }

    if (updatedEl && data.updated) {
      updatedEl.textContent = "Last updated: " + new Date(data.updated).toLocaleString();
    }

    if (!data.entries || data.entries.length === 0) {
      tbody.innerHTML =
        '<tr><td colspan="10" class="empty-state">No entries yet.</td></tr>';
      return;
    }

    // Sort by score descending
    data.entries.sort((a, b) => b.score - a.score);

    // Load all score files in parallel for detail panels
    const scoreFiles = {};
    await Promise.allSettled(
      data.entries.map(async (entry) => {
        try {
          scoreFiles[entry.team] = await fetchJSON(`scores/${entry.team}.json`);
        } catch {
          /* score file not copied yet, that's OK */
        }
      })
    );

    data.entries.forEach((entry, i) => {
      const row = buildRow(entry, i + 1);
      tbody.appendChild(row);

      const detailRow = buildDetailRow(scoreFiles[entry.team] || {});
      tbody.appendChild(detailRow);

      // Toggle detail on team name click
      row.querySelector("[data-team]").addEventListener("click", () => {
        detailRow.style.display =
          detailRow.style.display === "none" ? "table-row" : "none";
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
