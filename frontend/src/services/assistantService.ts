import { Person, TimelineEvent, ChatMessage } from '../types/investigation';

export const assistantService = {
  generateResponse(
    query: string,
    person: Person,
    timeline: TimelineEvent[],
    mode: 'ASSISTANCE' | 'DETECTIVE'
  ): ChatMessage {
    const q = query.toLowerCase().trim();
    const id = `msg-${Date.now()}`;
    const timestamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    if (mode === 'ASSISTANCE') {
      return this._generateFactualAssistance(id, q, person, timeline, timestamp);
    } else {
      return this._generateAnalyticalDetective(id, q, person, timeline, timestamp);
    }
  },

  _generateFactualAssistance(
    id: string,
    q: string,
    person: Person,
    timeline: TimelineEvent[],
    timestamp: string
  ): ChatMessage {
    // Intent 1: 'how many cases', 'cross', 'mentioned'
    if (q.includes('how many cases') || q.includes('cross') || q.includes('mentioned')) {
      const casesList = person.casesMentioned.join(', ');
      const crossEvents = timeline.filter(e => e.modality === 'CROSS_CASE');
      const refEv = crossEvents.map(e => e.evidenceId);

      return {
        id,
        sender: 'KRONOS_AI',
        mode: 'ASSISTANCE',
        timestamp,
        text: `[RECORDED FACTS]\n**${person.name} (${person.id})** is recorded across **${person.casesMentioned.length} cases**: ${casesList}. There are **${crossEvents.length} corroborated cross-case linkage events** on record connecting operations across police station jurisdictions.`,
        referencedCaseIds: person.casesMentioned,
        referencedPersonIds: [person.id],
        referencedEvidenceIds: refEv
      };
    }

    // Intent 2: 'primary', 'suspect'
    if (q.includes('primary') || q.includes('suspect')) {
      if (person.primarySuspectCases.length > 0) {
        return {
          id,
          sender: 'KRONOS_AI',
          mode: 'ASSISTANCE',
          timestamp,
          text: `[RECORDED FACTS]\n**${person.name}** is designated as the primary suspect in **${person.primarySuspectCases.length} cases**: ${person.primarySuspectCases.join(', ')}. In remaining dockets (${person.casesMentioned.filter(c => !person.primarySuspectCases.includes(c)).join(', ')}), ${person.name} is recorded as a person of interest or co-accused.`,
          referencedCaseIds: person.primarySuspectCases,
          referencedPersonIds: [person.id]
        };
      } else {
        return {
          id,
          sender: 'KRONOS_AI',
          mode: 'ASSISTANCE',
          timestamp,
          text: `[RECORDED FACTS]\n**${person.name}** is not recorded as a primary suspect in the current demonstration dataset. Recorded appearances are limited to association and financial conduit references.`,
          referencedPersonIds: [person.id]
        };
      }
    }

    // Intent 3: 'earliest', 'first' and 'latest', 'last', 'recent'
    if (q.includes('earliest') || q.includes('first')) {
      const ev = timeline[0];
      return {
        id,
        sender: 'KRONOS_AI',
        mode: 'ASSISTANCE',
        timestamp,
        text: `[RECORDED FACTS]\nFirst recorded appearance for **${person.name}** occurred on **${ev ? ev.dateStr : person.firstAppearance}** in **${ev ? ev.caseId : person.casesMentioned[0]}**: "${ev ? ev.title : 'Initial incident'}". Verified under record **${ev ? ev.evidenceId : 'EVD-0427-01'}**.`,
        referencedEventIds: ev ? [ev.id] : [],
        referencedEvidenceIds: ev ? [ev.evidenceId] : [],
        referencedCaseIds: ev ? [ev.caseId] : [person.casesMentioned[0]],
        referencedPersonIds: [person.id]
      };
    }

    if (q.includes('latest') || q.includes('last') || q.includes('recent')) {
      const ev = timeline[timeline.length - 1];
      return {
        id,
        sender: 'KRONOS_AI',
        mode: 'ASSISTANCE',
        timestamp,
        text: `[RECORDED FACTS]\nMost recent recorded activity for **${person.name}** occurred on **${ev ? ev.dateStr : person.latestActivity}** in **${ev ? ev.caseId : person.casesMentioned[0]}**: "${ev ? ev.title : 'Latest activity'}". Record reference: **${ev ? ev.evidenceId : 'EVD-0427-06'}**.`,
        referencedEventIds: ev ? [ev.id] : [],
        referencedEvidenceIds: ev ? [ev.evidenceId] : [],
        referencedCaseIds: ev ? [ev.caseId] : [person.casesMentioned[0]],
        referencedPersonIds: [person.id]
      };
    }

    // Intent 4: 'entity', 'associated', 'device', 'phone', 'account'
    if (q.includes('entity') || q.includes('associated') || q.includes('device') || q.includes('phone') || q.includes('account')) {
      return {
        id,
        sender: 'KRONOS_AI',
        mode: 'ASSISTANCE',
        timestamp,
        text: `[RECORDED FACTS]\nVerified associated entities for **${person.name} (${person.id})**:\n- **Contact Numbers**: ${person.contactNumbers.join(', ')}\n- **Seized / Triangulated Devices**: ${person.associatedDevices.join(', ')}\n- **Mule & Commercial Bank Accounts**: ${person.bankAccounts.join(', ')}\n- **Known Operational Bases**: ${person.knownLocations.join(' • ')}`,
        referencedPersonIds: [person.id, ...person.associatedPersonIds]
      };
    }

    // Intent 5: 'financial', 'money', 'transfer' (and month name)
    if (q.includes('financial') || q.includes('money') || q.includes('transfer') || q.includes('february') || q.includes('feb')) {
      const finEvents = timeline.filter(e => e.modality === 'FINANCIAL' || e.amount);
      if (finEvents.length > 0) {
        const ev = finEvents[0];
        return {
          id,
          sender: 'KRONOS_AI',
          mode: 'ASSISTANCE',
          timestamp,
          text: `[RECORDED FACTS]\nOn **${ev.dateStr} at ${ev.timeStr}**, banking logs in **${ev.caseId}** corroborate an outbound transfer of **₹${(ev.amount || 485000).toLocaleString('en-IN')}** routed through account **${person.bankAccounts[0] || 'ACC-7721'}**. Evidence record: **${ev.evidenceId}**.`,
          referencedEventIds: [ev.id],
          referencedEvidenceIds: [ev.evidenceId],
          referencedCaseIds: [ev.caseId],
          referencedPersonIds: [person.id]
        };
      }
    }

    // Intent 6: 'communication', 'call', 'sms'
    if (q.includes('communication') || q.includes('call') || q.includes('sms') || q.includes('phone')) {
      const commEvents = timeline.filter(e => e.modality === 'COMMUNICATION' || e.modality === 'CDR');
      if (commEvents.length > 0) {
        const ev = commEvents[0];
        return {
          id,
          sender: 'KRONOS_AI',
          mode: 'ASSISTANCE',
          timestamp,
          text: `[RECORDED FACTS]\nCommunication intercept recorded on **${ev.dateStr} (${ev.timeStr})** in **${ev.caseId}** between handset **${ev.deviceOrHardwareId || person.associatedDevices[0]}** and associate **${ev.counterpartyId || 'P-0299'}**. Evidence ID: **${ev.evidenceId}**.`,
          referencedEventIds: [ev.id],
          referencedEvidenceIds: [ev.evidenceId],
          referencedCaseIds: [ev.caseId],
          referencedPersonIds: [person.id, ev.counterpartyId || 'P-0299']
        };
      }
    }

    // Intent 7: Month name or date
    const months = ['january', 'jan', 'february', 'feb', 'march', 'mar', 'april', 'apr'];
    const matchedMonth = months.find(m => q.includes(m));
    if (matchedMonth) {
      const shortM = matchedMonth.slice(0, 3).toUpperCase();
      const mEvents = timeline.filter(e => e.monthStr.toUpperCase().includes(shortM) || e.dateStr.toUpperCase().includes(shortM));
      if (mEvents.length > 0) {
        const evList = mEvents.map(e => `• ${e.dateStr} — ${e.title} (${e.evidenceId})`).join('\n');
        return {
          id,
          sender: 'KRONOS_AI',
          mode: 'ASSISTANCE',
          timestamp,
          text: `[RECORDED FACTS]\nEvents recorded in **${shortM}** for **${person.name}**:\n${evList}`,
          referencedEventIds: mEvents.map(e => e.id),
          referencedEvidenceIds: mEvents.map(e => e.evidenceId),
          referencedPersonIds: [person.id]
        };
      }
    }

    // Intent 8: 'summarise', 'activity', 'overview'
    if (q.includes('summarise') || q.includes('summarize') || q.includes('activity') || q.includes('overview')) {
      return {
        id,
        sender: 'KRONOS_AI',
        mode: 'ASSISTANCE',
        timestamp,
        text: `[RECORDED FACTS]\nActivity summary for **${person.name} (${person.id})**:\n- **Recorded Date Range**: ${person.firstAppearance} to ${person.latestActivity}\n- **Case Involvement**: Referenced in ${person.casesMentioned.length} dockets (${person.casesMentioned.join(', ')}), primary suspect in ${person.primarySuspectCases.length}.\n- **Evidence Count**: ${timeline.length} corroborated timeline milestones spanning FIR registration, communications, cellular location triangulation, and banking RTGS trails.`,
        referencedCaseIds: person.casesMentioned,
        referencedPersonIds: [person.id],
        referencedEvidenceIds: timeline.slice(0, 3).map(e => e.evidenceId)
      };
    }

    // Default intent fallback
    return {
      id,
      sender: 'KRONOS_AI',
      mode: 'ASSISTANCE',
      timestamp,
      text: `[RECORDED FACTS]\nThe requested query is not explicitly recorded in the demonstration dataset for **${person.name} (${person.id})**. Available records cover registered FIRs, verified CDR pings, bank ledger transfers, and spatial co-locations.`,
      referencedPersonIds: [person.id]
    };
  },

  _generateAnalyticalDetective(
    id: string,
    q: string,
    person: Person,
    timeline: TimelineEvent[],
    timestamp: string
  ): ChatMessage {
    // Detective mode: Pattern, Possible Lead, Alternative Explanation (never asserts guilt or probability)
    return {
      id,
      sender: 'KRONOS_AI',
      mode: 'DETECTIVE',
      timestamp,
      text: `[DEMO ANALYSIS, HYPOTHESIS, NOT FACT]\n\n**Possible Pattern**:\nCorrelated CDR cell-site logs indicate repetitive co-presence between ${person.id} and associate nodes (P-0299, P-0384) in the Delhi-Ambala transit corridor 48 hours prior to recorded financial wire dispersals.\n\n**Investigative Lead**:\nExamine KYC identity documentation for prepaid SIM profiles operating on IMEI associated with ${person.associatedDevices[0] || 'DEV-8849'} to establish secondary couriers.\n\n**Alternative Explanation**:\nDevice mobility may reflect commercial transport route logistics rather than coordinated syndicate movement; third-party handset possession cannot be eliminated from electronic records alone.`,
      referencedCaseIds: person.casesMentioned,
      referencedPersonIds: [person.id, 'P-0299', 'P-0384'],
      referencedEvidenceIds: timeline.length > 0 ? [timeline[0].evidenceId] : [],
      isAnalyticalHypothesis: true
    };
  }
};
