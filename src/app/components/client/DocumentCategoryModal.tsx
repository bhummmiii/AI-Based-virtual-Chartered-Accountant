/**
 * DocumentCategoryModal — Step 1
 * Shows all 13 GST document categories. User picks one,
 * then parent opens either Upload or Scan modal.
 */
import {
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle,
} from "../ui/dialog";

export type DocAction = "upload" | "scan";

export interface DocumentCategory {
  id: string;
  label: string;
  altLabel?: string;
  description: string;
  usedFor: string[];
  supported?: string[];
  icon: string;
}

export const DOCUMENT_CATEGORIES: DocumentCategory[] = [
  {
    id: "sales_records",
    label: "Sales Records",
    description: "Sales invoices and outward supply documents.",
    usedFor: ["GSTR-1", "Sales Register", "Revenue", "GST Output Tax"],
    icon: "📤",
  },
  {
    id: "purchase_records",
    label: "Purchase Records",
    description: "Purchase invoices and inward supply documents.",
    usedFor: ["Purchase Register", "Input GST", "ITC", "GSTR-2B Reconciliation"],
    icon: "📥",
  },
  {
    id: "credit_note",
    label: "Sales Return",
    altLabel: "Credit Note",
    description: "Customer returned goods.",
    usedFor: ["Credit Note", "GST Adjustment", "Sales Return Register"],
    icon: "↩️",
  },
  {
    id: "debit_note",
    label: "Purchase Return",
    altLabel: "Debit Note",
    description: "Returned goods to supplier.",
    usedFor: ["Debit Note", "GST Adjustment", "Purchase Return Register"],
    icon: "↪️",
  },
  {
    id: "b2b_invoice",
    label: "B2B Invoice",
    description: "GST invoices issued to registered businesses.",
    usedFor: ["GSTIN", "HSN", "Taxable Value", "CGST/SGST/IGST"],
    icon: "🏢",
  },
  {
    id: "b2c_invoice",
    label: "B2C Invoice",
    description: "GST invoices issued to consumers.",
    usedFor: ["Customer", "Invoice", "Tax", "Amount", "HSN"],
    icon: "👤",
  },
  {
    id: "hsn_sac",
    label: "HSN / SAC List",
    description: "Upload HSN/SAC master data.",
    usedFor: ["HSN Codes", "SAC Codes", "Rate Mapping"],
    supported: ["CSV", "Excel", "JSON"],
    icon: "📋",
  },
  {
    id: "e_invoice",
    label: "E-Invoice",
    description: "Upload IRN-enabled GST e-Invoice.",
    usedFor: ["IRN", "QR Code", "GST Compliance"],
    supported: ["JSON", "PDF", "XML"],
    icon: "⚡",
  },
  {
    id: "e_way_bill",
    label: "E-Way Bill",
    description: "Upload E-Way Bill for goods transport.",
    usedFor: ["Transport", "Logistics", "GST Compliance"],
    supported: ["PDF", "JSON", "XML"],
    icon: "🚚",
  },
  {
    id: "gst_challan",
    label: "GST Challan",
    description: "Upload GST payment challans.",
    usedFor: ["Tax Payment", "Challan Reference", "CIN"],
    supported: ["PDF"],
    icon: "💳",
  },
  {
    id: "gst_return",
    label: "GST Return",
    description: "Upload filed GST Returns.",
    usedFor: ["GSTR-1", "GSTR-3B", "Annual Return"],
    supported: ["PDF", "JSON"],
    icon: "📊",
  },
  {
    id: "gst_notice",
    label: "GST Notice",
    description: "Upload GST Notices received from department.",
    usedFor: ["Notice Response", "Compliance", "Department Communication"],
    supported: ["PDF"],
    icon: "📨",
  },
  {
    id: "document_list",
    label: "Document List",
    description: "General GST compliance documents.",
    usedFor: ["Registration Certificate", "GST Certificate", "PAN", "Business License"],
    supported: ["PDF", "DOCX", "Images", "ZIP"],
    icon: "📁",
  },
];

interface Props {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  action: DocAction;
  onSelect: (category: DocumentCategory) => void;
}

export function DocumentCategoryModal({ open, onOpenChange, action, onSelect }: Props) {
  const title = action === "upload" ? "Upload Document" : "Scan Document";
  const subtitle = "Choose the type of document you want to " + (action === "upload" ? "upload." : "scan.");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Select Document Category</DialogTitle>
          <DialogDescription>{subtitle}</DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-1 gap-3 py-2 sm:grid-cols-2">
          {DOCUMENT_CATEGORIES.map((cat) => (
            <button
              key={cat.id}
              type="button"
              onClick={() => {
                onSelect(cat);
                onOpenChange(false);
              }}
              className="flex items-start gap-3 rounded-xl border border-border p-4 text-left transition-colors hover:border-primary/50 hover:bg-secondary/50 focus:outline-none focus:ring-2 focus:ring-primary/40"
            >
              <span className="mt-0.5 text-xl">{cat.icon}</span>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium leading-tight">
                  {cat.label}
                  {cat.altLabel && (
                    <span className="ml-1 text-xs text-muted-foreground">/ {cat.altLabel}</span>
                  )}
                </p>
                <p className="mt-0.5 text-xs text-muted-foreground leading-snug">{cat.description}</p>
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {cat.usedFor.slice(0, 3).map((u) => (
                    <span key={u} className="rounded bg-secondary px-1.5 py-0.5 text-[10px] text-muted-foreground">
                      {u}
                    </span>
                  ))}
                </div>
              </div>
            </button>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}
