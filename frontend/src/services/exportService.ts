import { Case, TimelineEvent, EvidenceRecord } from '../types/investigation';

export const exportService = {
  downloadFile(content: string, filename: string, mimeType: string) {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  },

  exportCaseSummary(c: Case, evidence: EvidenceRecord[]) {
    const lines = [
      `================================================================================`,
      `KRONOS DIGITAL INVESTIGATION INTELLIGENCE REPORT`,
      `CASE FILE: ${c.id} — ${c.title.toUpperCase()}`,
      `Generated: ${new Date().toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' })} IST`,
      `Classification: CONFIDENTIAL // LAW ENFORCEMENT DEMO`,
      `================================================================================\n`,
      `1. CASE OVERVIEW`,
      `----------------`,
      `Offence Category : ${c.offenceCategory}`,
      `Status           : ${c.status}`,
      `Priority         : ${c.priority}`,
      `FIR Reference    : ${c.firNumber} (${c.policeStation}, ${c.district})`,
      `Incident Date    : ${c.incidentDate}`,
      `Registration Date: ${c.registrationDate} (Delay: ${c.reportingDelayHours} hrs)`,
      `Lead Officer     : ${c.leadInvestigator}`,
      `Financial Volume : ₹${c.totalFinancialVolume.toLocaleString('en-IN')}`,
      `Associated People: ${c.peopleCount}`,
      `Total Evidence   : ${c.evidenceCount} records\n`,
      `2. CASE NARRATIVE`,
      `-----------------`,
      `${c.description}\n`,
      `3. IDENTIFIED SUSPECTS & PERSONS OF INTEREST`,
      `--------------------------------------------`,
      `Primary Suspects : ${c.primarySuspectIds.join(', ') || 'Under evaluation'}`,
      `Connected Persons: ${c.personIds.join(', ')}\n`,
      `4. CORROBORATING EVIDENCE LOG (${evidence.length} entries)`,
      `-------------------------------------------------------`
    ];

    evidence.forEach((ev, idx) => {
      lines.push(
        `[${idx + 1}] ${ev.evidenceId} | Modality: ${ev.modality} | Source: ${ev.sourceReliability}`,
        `    Timestamp  : ${ev.timestamp}`,
        `    Location   : ${ev.locationName}`,
        `    Description: ${ev.description}`,
        `    Persons    : ${ev.relatedPersonIds.join(', ')}`,
        ``
      );
    });

    lines.push(
      `================================================================================`,
      `END OF REPORT — KRONOS AI DIGITAL INVESTIGATION ASSISTANT`,
      `================================================================================`
    );

    this.downloadFile(lines.join('\n'), `${c.id}_investigation_summary.txt`, 'text/plain');
  },

  exportTimelineCSV(timeline: TimelineEvent[], personName: string) {
    const headers = ['Event ID', 'Date', 'Time', 'Modality', 'Title', 'Case ID', 'Evidence ID', 'Location', 'Amount INR', 'Counterparty', 'Device ID', 'Severity', 'Description'];
    const rows = timeline.map(e => [
      `"${e.id}"`,
      `"${e.dateStr}"`,
      `"${e.timeStr}"`,
      `"${e.modality}"`,
      `"${e.title.replace(/"/g, '""')}"`,
      `"${e.caseId}"`,
      `"${e.evidenceId}"`,
      `"${(e.locationName || '').replace(/"/g, '""')}"`,
      `"${e.amount || ''}"`,
      `"${e.counterpartyId || ''}"`,
      `"${e.deviceOrHardwareId || ''}"`,
      `"${e.severity || 'NORMAL'}"`,
      `"${e.description.replace(/"/g, '""')}"`
    ]);

    const csvContent = [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
    const sanitized = personName.replace(/\s+/g, '_').toLowerCase();
    this.downloadFile(csvContent, `${sanitized}_timeline_${new Date().toISOString().slice(0, 10)}.csv`, 'text/csv');
  },

  exportEvidenceJSON(evidence: EvidenceRecord[]) {
    const jsonStr = JSON.stringify({
      exportMetadata: {
        system: 'KRONOS Digital Investigation Assistant',
        exportedAt: new Date().toISOString(),
        totalRecords: evidence.length,
        version: '1.0.0-demo'
      },
      evidenceRecords: evidence
    }, null, 2);

    this.downloadFile(jsonStr, `kronos_evidence_archive_${new Date().toISOString().slice(0, 10)}.json`, 'application/json');
  },

  exportEvidenceAsJson(evidence: EvidenceRecord | EvidenceRecord[]) {
    const list = Array.isArray(evidence) ? evidence : [evidence];
    this.exportEvidenceJSON(list);
  }
};
