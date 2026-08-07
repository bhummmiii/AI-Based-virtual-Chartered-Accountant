// ============================================================
// DocumentCategoryModal — Pick one of the 13 GST categories
// ============================================================
import React from "react";
import { DOCUMENT_CATEGORIES } from "../../../types/document.types";
import type { DocumentCategory } from "../../../types/document.types";

interface Props {
  onSelect: (category: DocumentCategory) => void;
  onClose: () => void;
}

export const DocumentCategoryModal: React.FC<Props> = ({ onSelect, onClose }) => {
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-card doc-cat-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2 className="modal-title">Select Document Category</h2>
          <button className="modal-close" onClick={onClose} aria-label="Close">?</button>
        </div>
        <p className="modal-subtitle">Choose the type of GST document you want to add</p>
        <div className="cat-grid">
          {DOCUMENT_CATEGORIES.map((cat) => (
            <button
              key={cat.id}
              className="cat-tile"
              onClick={() => onSelect(cat.id as DocumentCategory)}
            >
              <span className="cat-icon">{cat.icon}</span>
              <span className="cat-label">{cat.label}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
};
