import { Button } from "@heroui/react";
import { BookOpen, Eye } from "lucide-react";
import type { SopEntry } from "../api";

type SopListItemProps = {
  sop: SopEntry;
  isSelected?: boolean;
  onOpen: (sop: SopEntry) => void;
  onPreview?: (sop: SopEntry) => void;
  variant?: "picker" | "library";
};

export function SopListItem({ sop, isSelected = false, onOpen, onPreview, variant = "picker" }: SopListItemProps) {
  const className = `${variant === "library" ? "sop-library-item" : "sop-picker-item"} ${isSelected ? "is-selected" : ""}`;

  return (
    <div className={className}>
      <button className="sop-picker-main" onClick={() => onOpen(sop)} type="button">
        <span className="sop-picker-icon" aria-hidden="true">
          <BookOpen size={15} />
        </span>
        <span className="sop-picker-copy">
          <span className="sop-picker-title-row">
            <span className="sop-picker-title">{sop.title || sop.name}</span>
            <span className="sop-picker-file">@{sop.id}</span>
          </span>
          <span className="sop-picker-meta">{sop.path}</span>
          {sop.summary ? <span className="sop-picker-summary">{sop.summary}</span> : null}
        </span>
      </button>
      {onPreview ? (
        <Button
          aria-label={`查看 ${sop.name}`}
          className="sop-picker-preview-button"
          isIconOnly
          onPress={() => onPreview(sop)}
          size="sm"
          variant="ghost"
        >
          <Eye size={14} />
        </Button>
      ) : null}
    </div>
  );
}
