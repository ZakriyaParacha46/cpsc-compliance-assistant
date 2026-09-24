/** rule = 16 CFR regulation, law = statute (U.S. Code), guidance = CPSC explainer pages. */
export type SourceType = "rule" | "law" | "guidance";

export interface Section {
  id: string; // CFR section number, e.g. "1263.3"
  heading: string;
  text: string;
}

export interface DocSummary {
  id: string;
  source_type: SourceType;
  cfr_part: string | null;
  title: string;
  url: string;
  as_of: string;
  section_count: number;
}

export interface DocFull extends Omit<DocSummary, "section_count"> {
  sections: Section[];
  note?: string;
}

/** One numbered source the answer cites. start/end are offsets into the section text. */
export interface Citation {
  n: number;
  chunk_id: string;
  doc_id: string;
  doc_title?: string;
  section: string;
  source_type: SourceType;
  title: string;
  url: string;
  start: number;
  end: number;
}

export interface Usage {
  used: number;
  limit: number;
  resets_at: string;
}

export type AnswerStatus = "answered" | "not_covered" | "off_topic";

/** SSE events from POST /api/ask, in order: sources, token*, done (or error). */
export type AskEvent =
  | { type: "sources"; query_id: string; citations: Citation[] } // everything retrieved
  | { type: "token"; text: string }
  | {
      type: "done";
      query_id: string;
      status: AnswerStatus;
      cited: number[]; // source numbers the answer actually cites
      standards: string[]; // paid standards named in cited sources (text not included)
      usage: Usage;
      reason?: string; // why it was refused; sent in dev only, never in prod
    }
  | { type: "error"; code: string; message: string; retry_after?: number };
