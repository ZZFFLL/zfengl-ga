import { Button } from "@heroui/react";
import { BookOpen, Eye } from "lucide-react";
import type { SopEntry } from "../api";

type SopPickerItemProps = {
  sop: SopEntry;
  isActive?: boolean;
  isSelected?: boolean;
  onOpen: (sop: SopEntry) => void;
  onPreview?: (sop: SopEntry) => void;
};

export function SopPickerItem({ sop, isActive = false, isSelected = false, onOpen, onPreview }: SopPickerItemProps) {
  return (
    // 弹窗列表保持独立 class，避免被 SOP 库页面的可变高度样式污染。
    <div className={`sop-picker-item ${isActive ? "is-active" : ""} ${isSelected ? "is-selected" : ""}`}>
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
          <span className="sop-picker-summary">{sop.summary || "暂无摘要"}</span>
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
