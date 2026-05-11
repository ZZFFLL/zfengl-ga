import type { ReactNode } from "react";
import { Drawer } from "antd";

export function SidebarDialog({
  open,
  onOpenChange,
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  children: ReactNode;
}) {
  return (
    <Drawer
      open={open}
      placement="left"
      width="min(92vw, 21.25rem)"
      title="会话列表"
      aria-label="会话列表"
      className="ga-sidebar-drawer xl:hidden"
      styles={{
        body: { padding: 0 },
        header: { borderBottom: "0.0625rem solid #d8deeb" },
      }}
      onClose={() => onOpenChange(false)}
    >
      {children}
    </Drawer>
  );
}
