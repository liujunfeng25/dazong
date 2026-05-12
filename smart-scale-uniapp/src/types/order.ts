export interface OrderRow {
  id: string;
  name: string;
  qty: string;
  unit: string;
  /** 后端 order_items.receiving_status */
  receivingStatus?: string | null;
  receivingConfirmedKg?: number | null;
  receivingDraftKg?: number | null;
  /** 少收原因草稿（lack/quality/other） */
  shortageReasonCode?: string | null;
  shortageReasonDetail?: string | null;
  lineNo?: number;
}

export interface OrderBrief {
  id: string;
  order_no?: string;
  status?: string;
  title: string;
  lines: OrderRow[];
  receivingConfirmedCount?: number;
  receivingTotalLines?: number;
  receiveSignaturesJson?: Record<string, unknown> | null;
  /** 收货后生成的退货单摘要（GET /orders/:id） */
  orderReturn?: {
    return_no: string;
    lines: Array<{
      line_index: number;
      reason_code: string;
      reason_detail?: string | null;
      delta_kg: number;
    }>;
  } | null;
}
