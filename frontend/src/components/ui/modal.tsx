import { useEffect, useCallback } from "react"
import { X } from "lucide-react"
import { cn } from "@/lib/utils"

interface ModalProps {
  open: boolean
  onClose: () => void
  title?: React.ReactNode
  footer?: React.ReactNode
  width?: string | number
  children: React.ReactNode
  className?: string
  maskClosable?: boolean
}

export function Modal({
  open,
  onClose,
  title,
  footer,
  width = 520,
  children,
  className,
  maskClosable = true,
}: ModalProps) {
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose()
    },
    [onClose]
  )

  useEffect(() => {
    if (open) {
      document.addEventListener("keydown", handleKeyDown)
      document.body.style.overflow = "hidden"
    }
    return () => {
      document.removeEventListener("keydown", handleKeyDown)
      document.body.style.overflow = ""
    }
  }, [open, handleKeyDown])

  if (!open) return null

  const widthStyle = typeof width === "number" ? `${width}px` : width

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/50 transition-opacity"
        onClick={maskClosable ? onClose : undefined}
      />

      {/* Modal */}
      <div
        className={cn(
          "relative z-50 max-h-[85vh] overflow-auto rounded-lg bg-background shadow-lg",
          "animate-in fade-in-0 zoom-in-95",
          className
        )}
        style={{ width: widthStyle, maxWidth: "calc(100vw - 32px)" }}
      >
        {/* Header */}
        {title && (
          <div className="flex items-center justify-between border-b px-6 py-4">
            <h2 className="text-lg font-semibold">{title}</h2>
            <button
              onClick={onClose}
              className="rounded-sm opacity-70 transition-opacity hover:opacity-100"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
        )}

        {/* Body */}
        <div className="px-6 py-4">{children}</div>

        {/* Footer */}
        {footer && (
          <div className="flex items-center justify-end gap-2 border-t px-6 py-4">
            {footer}
          </div>
        )}
      </div>
    </div>
  )
}
