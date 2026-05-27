import { Button } from "@heroui/react";
import { BookOpen, Eye } from "lucide-react";
import type { SopEntry } from "../api";

type SopWorkspaceItemProps = {
  sop: SopEntry;
  isSelected?: boolean;
  onOpen: (sop: SopEntry) => void;
  onPreview?: (sop: SopEntry) => void;
};

export function SopWorkspaceItem({ sop, isSelected = false, onOpen, onPreview }: SopWorkspaceItemProps) {
  return (
    // SOP 库列表独立于对话框 picker，页面三栏收缩时可按自然高度换行。
    <div className={`sop-library-item ${isSelected ? "is-selected" : ""}`}>
      <button className="sop-library-main" onClick={() => onOpen(sop)} type="button">
        <span className="sop-library-icon" aria-hidden="true">
          <BookOpen size={15} />
        </span>
        <span className="sop-library-copy">
          <span className="sop-library-title-row">
            <span className="sop-library-title">{sop.title || sop.name}</span>
            <span className="sop-library-file">@{sop.id}</span>
          </span>
          <span className="sop-library-meta">{sop.path}</span>
          <span className="sop-library-summary">{sop.summary || "暂无摘要"}</span>
        </span>
      </button>
      {onPreview ? (
        <Button
          aria-label={`查看 ${sop.name}`}
          className="sop-library-preview-button"
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
