import { useState, useRef, useEffect } from "react"
import { ChevronDown } from "lucide-react"
import { cn } from "@/lib/utils"

interface DropdownItem {
  key: string
  label: React.ReactNode
  icon?: React.ReactNode
  disabled?: boolean
  danger?: boolean
  onClick?: () => void
}

interface DropdownProps {
  items: DropdownItem[]
  trigger?: React.ReactNode
  children?: React.ReactNode
  placement?: "bottomLeft" | "bottomRight" | "topLeft" | "topRight"
  className?: string
}

export function Dropdown({
  items,
  trigger,
  children,
  placement = "bottomLeft",
  className,
}: DropdownProps) {
  const [open, setOpen] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener("mousedown", handleClickOutside)
    return () => document.removeEventListener("mousedown", handleClickOutside)
  }, [])

  const placementClasses = {
    bottomLeft: "top-full left-0 mt-1",
    bottomRight: "top-full right-0 mt-1",
    topLeft: "bottom-full left-0 mb-1",
    topRight: "bottom-full right-0 mb-1",
  }

  return (
    <div ref={dropdownRef} className={cn("relative inline-block", className)}>
      <div onClick={() => setOpen(!open)} className="cursor-pointer">
        {trigger || children || (
          <button className="flex items-center gap-1 rounded px-3 py-1.5 text-sm hover:bg-accent">
            Options
            <ChevronDown className="h-4 w-4" />
          </button>
        )}
      </div>

      {open && (
        <div
          className={cn(
            "absolute z-50 min-w-[160px] rounded-md border bg-background p-1 shadow-md",
            "animate-in fade-in-0 zoom-in-95",
            placementClasses[placement]
          )}
        >
          {items.map((item) => (
            <button
              key={item.key}
              disabled={item.disabled}
              onClick={() => {
                item.onClick?.()
                setOpen(false)
              }}
              className={cn(
                "flex w-full items-center gap-2 rounded-sm px-3 py-2 text-sm",
                "transition-colors hover:bg-accent",
                item.disabled && "cursor-not-allowed opacity-50",
                item.danger && "text-destructive hover:bg-destructive/10"
              )}
            >
              {item.icon}
              {item.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
