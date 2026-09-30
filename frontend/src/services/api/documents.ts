// ============================================================
// Document Management API Service
// ============================================================

import apiClient from "./client";
import type {
  UploadedDocument,
  DocumentUploadPayload,
  OcrExtractResponse,
  DuplicateResponse,
} from "../../types/document.types";

const BASE = "/invoices";
const OCR_BASE = "/ocr";

// -- Types -----------------------------------------------------
interface ApiResponse<T> {
  success: boolean;
  data: T;
  message: string;
}

export interface UploadResult {
  type: "success";
  document: UploadedDocument;
}

export interface DuplicateResult {
  type: "duplicate";
  info: DuplicateResponse;
}

export type UploadDocumentResult = UploadResult | DuplicateResult;

// -- Upload document -------------------------------------------
export async function uploadDocument(
  clientId: string,
  payload: DocumentUploadPayload
): Promise<UploadDocumentResult> {
  const fd = new FormData();
  (Object.keys(payload) as Array<keyof DocumentUploadPayload>).forEach((key) => {
    const val = payload[key];
    if (val === undefined || val === null) return;
    if (val instanceof File) {
      fd.append("file", val);
    } else {
      fd.append(String(key), String(val));
    }
  });

  try {
    const res = await apiClient.post<ApiResponse<UploadedDocument>>(
      `${BASE}/${clientId}/upload`,
      fd,
      { headers: { "Content-Type": "multipart/form-data" } }
    );
    return { type: "success", document: res.data.data };
  } catch (err: unknown) {
    const axiosErr = err as { response?: { status?: number; data?: DuplicateResponse } };
    if (axiosErr.response?.status === 409) {
      return { type: "duplicate", info: axiosErr.response.data! };
    }
    throw err;
  }
}

// -- List documents for client ---------------------------------
export async function listDocuments(
  clientId: string,
  filters?: { category?: string; document_type?: string; status?: string }
): Promise<UploadedDocument[]> {
  const params = filters ?? {};
  const res = await apiClient.get<ApiResponse<UploadedDocument[]>>(
    `${BASE}/${clientId}`,
    { params }
  );
  return res.data.data;
}

// -- Get single document ---------------------------------------
export async function getDocument(docId: string): Promise<UploadedDocument> {
  const res = await apiClient.get<ApiResponse<UploadedDocument>>(
    `${BASE}/document/${docId}`
  );
  return res.data.data;
}

// -- Delete document -------------------------------------------
export async function deleteDocument(docId: string): Promise<void> {
  await apiClient.delete(`${BASE}/document/${docId}`);
}

// -- OCR Extract -----------------------------------------------
export async function ocrExtract(
  file: File,
  category: string
): Promise<OcrExtractResponse> {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("category", category);
  const res = await apiClient.post<OcrExtractResponse>(
    `${OCR_BASE}/extract`,
    fd,
    { headers: { "Content-Type": "multipart/form-data" }, timeout: 120000 }
  );
  return res.data;
}
