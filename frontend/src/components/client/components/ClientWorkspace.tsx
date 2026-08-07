// ============================================================
// ClientWorkspace — Full document management workspace for one client
// ============================================================
import React, { useEffect, useState, useCallback } from "react";
import { useParams } from "react-router-dom";
import type { DocumentCategory, UploadedDocument } from "../../../types/document.types";
import { DOCUMENT_CATEGORIES } from "../../../types/document.types";
import { listDocuments, deleteDocument } from "../../../services/api/documents";
import { DocumentCategoryModal } from "./DocumentCategoryModal";
import { UploadDocumentModal } from "./UploadDocumentModal";
import { ScanDocumentModal } from "./ScanDocumentModal";

// -- Types -----------------------------------------------------
type ModalState =
  | { type: "none" }
  | { type: "category-upload" }
  | { type: "category-scan" }
  | { type: "upload"; category: DocumentCategory }
  | { type: "scan";   category: DocumentCategory };

// -- Status badge ----------------------------------------------
const StatusBadge: React.FC<{ status: string }> = ({ status }) => {
  const map: Record<string, string> = {
    pending:   "badge-pending",
    processed: "badge-processed",
    verified:  "badge-verified",
    rejected:  "badge-rejected",
  };
  return <span className={`status-badge ${map[status] ?? "badge-pending"}`}>{status}</span>;
};

// -- OCR Status badge ------------------------------------------
const OcrBadge: React.FC<{ status?: string }> = ({ status }) => {
  if (!status || status === "pending") return null;
  const map: Record<string, { label: string; cls: string }> = {
    done:       { label: "OCR Done",       cls: "ocr-done" },
    processing: { label: "Processing…",    cls: "ocr-processing" },
    failed:     { label: "OCR Failed",     cls: "ocr-failed" },
  };
  const info = map[status];
  return info ? <span className={`ocr-status-badge ${info.cls}`}>{info.label}</span> : null;
};

// -- Main Component --------------------------------------------
export const ClientWorkspace: React.FC = () => {
  const { clientId } = useParams<{ clientId: string }>();
  const [docs, setDocs] = useState<UploadedDocument[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [modal, setModal] = useState<ModalState>({ type: "none" });
  const [filterCat, setFilterCat] = useState<string>("");
  const [search, setSearch] = useState("");
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [toastMsg, setToastMsg] = useState<string | null>(null);

  const showToast = (msg: string) => {
    setToastMsg(msg);
    setTimeout(() => setToastMsg(null), 3000);
  };

  const fetchDocs = useCallback(async () => {
    if (!clientId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await listDocuments(clientId, filterCat ? { category: filterCat } : {});
      setDocs(data);
    } catch {
      setError("Failed to load documents");
    } finally {
      setLoading(false);
    }
  }, [clientId, filterCat]);

  useEffect(() => { fetchDocs(); }, [fetchDocs]);

  const handleDelete = async (docId: string) => {
    if (!window.confirm("Delete this document?")) return;
    setDeletingId(docId);
    try {
      await deleteDocument(docId);
      showToast("Document deleted");
      fetchDocs();
    } catch {
      showToast("Failed to delete document");
    } finally {
      setDeletingId(null);
    }
  };

  const handleSuccess = () => {
    setModal({ type: "none" });
    fetchDocs();
    showToast("Document saved successfully! ?");
  };

  // Filtered docs
  const filtered = docs.filter((d) => {
    const s = search.toLowerCase();
    if (!s) return true;
    return (
      d.invoice_number?.toLowerCase().includes(s) ||
      d.vendor?.toLowerCase().includes(s) ||
      d.customer?.toLowerCase().includes(s) ||
      d.gstin?.toLowerCase().includes(s) ||
      d.document_category.toLowerCase().includes(s)
    );
  });

  const getCatLabel = (id: string) =>
    DOCUMENT_CATEGORIES.find((c) => c.id === id)?.label ?? id;
  const getCatIcon = (id: string) =>
    DOCUMENT_CATEGORIES.find((c) => c.id === id)?.icon ?? "??";

  return (
    <div className="workspace-root">
      {/* -- Toolbar ----------------------------------- */}
      <div className="workspace-toolbar">
        <div className="toolbar-left">
          <h1 className="workspace-title">Document Workspace</h1>
          <span className="doc-count">{docs.length} document{docs.length !== 1 ? "s" : ""}</span>
        </div>
        <div className="toolbar-right">
          <input
            className="search-input"
            placeholder="Search by invoice #, vendor, GSTIN…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <select
            className="filter-select"
            value={filterCat}
            onChange={(e) => setFilterCat(e.target.value)}
          >
            <option value="">All Categories</option>
            {DOCUMENT_CATEGORIES.map((c) => (
              <option key={c.id} value={c.id}>{c.icon} {c.label}</option>
            ))}
          </select>
          <button
            className="btn btn-secondary"
            onClick={() => setModal({ type: "category-scan" })}
          >
            ?? Scan
          </button>
          <button
            className="btn btn-primary"
            onClick={() => setModal({ type: "category-upload" })}
          >
            + Upload
          </button>
        </div>
      </div>

      {/* -- Content ------------------------------------ */}
      {loading && (
        <div className="loading-state">
          <div className="loading-spinner" />
          <p>Loading documents…</p>
        </div>
      )}

      {error && <div className="error-banner workspace-error">{error}</div>}

      {!loading && !error && filtered.length === 0 && (
        <div className="empty-state">
          <div className="empty-icon">??</div>
          <p className="empty-title">{docs.length === 0 ? "No documents yet" : "No matching documents"}</p>
          <p className="empty-sub">
            {docs.length === 0
              ? "Upload or scan your first GST document to get started"
              : "Try a different search term or category filter"}
          </p>
          {docs.length === 0 && (
            <div className="empty-actions">
              <button className="btn btn-secondary" onClick={() => setModal({ type: "category-scan" })}>?? Scan Document</button>
              <button className="btn btn-primary" onClick={() => setModal({ type: "category-upload" })}>+ Upload Document</button>
            </div>
          )}
        </div>
      )}

      {!loading && filtered.length > 0 && (
        <div className="doc-table-wrapper">
          <table className="doc-table">
            <thead>
              <tr>
                <th>Category</th>
                <th>Invoice # / Ref</th>
                <th>Vendor / Customer</th>
                <th>GSTIN</th>
                <th>Date</th>
                <th>Amount</th>
                <th>Status</th>
                <th>OCR</th>
                <th>File</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((doc) => (
                <tr key={doc.id} className="doc-row">
                  <td>
                    <span className="cat-chip">
                      {getCatIcon(doc.document_category)} {getCatLabel(doc.document_category)}
                    </span>
                  </td>
                  <td className="mono-cell">
                    {doc.invoice_number ?? doc.notice_number ?? doc.arn ?? "—"}
                  </td>
                  <td>{doc.vendor ?? doc.customer ?? "—"}</td>
                  <td className="mono-cell">{doc.gstin ?? "—"}</td>
                  <td>{doc.invoice_date ?? doc.notice_date ?? doc.filed_date ?? "—"}</td>
                  <td className="amount-cell">
                    {doc.amount != null ? `?${Number(doc.amount).toLocaleString("en-IN")}` : "—"}
                  </td>
                  <td><StatusBadge status={doc.status} /></td>
                  <td><OcrBadge status={doc.ocr_status} /></td>
                  <td>
                    {doc.file_name ? (
                      <span className="file-chip" title={doc.file_name}>
                        ?? {doc.file_type?.toUpperCase() ?? "FILE"}
                      </span>
                    ) : "—"}
                  </td>
                  <td>
                    <div className="row-actions">
                      <button
                        className="action-btn action-delete"
                        onClick={() => handleDelete(doc.id)}
                        disabled={deletingId === doc.id}
                        title="Delete"
                      >
                        {deletingId === doc.id ? "…" : "??"}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* -- Toast -------------------------------------- */}
      {toastMsg && <div className="toast">{toastMsg}</div>}

      {/* -- Modals ------------------------------------- */}
      {modal.type === "category-upload" && (
        <DocumentCategoryModal
          onSelect={(cat) => setModal({ type: "upload", category: cat })}
          onClose={() => setModal({ type: "none" })}
        />
      )}
      {modal.type === "category-scan" && (
        <DocumentCategoryModal
          onSelect={(cat) => setModal({ type: "scan", category: cat })}
          onClose={() => setModal({ type: "none" })}
        />
      )}
      {modal.type === "upload" && (
        <UploadDocumentModal
          clientId={clientId!}
          category={modal.category}
          onClose={() => setModal({ type: "none" })}
          onSuccess={handleSuccess}
        />
      )}
      {modal.type === "scan" && (
        <ScanDocumentModal
          clientId={clientId!}
          category={modal.category}
          onClose={() => setModal({ type: "none" })}
          onSuccess={handleSuccess}
        />
      )}
    </div>
  );
};
