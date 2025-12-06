import { useState } from "react"
import { cn } from "@/lib/utils"

interface TabItem {
  key: string
  label: React.ReactNode
  children: React.ReactNode
  disabled?: boolean
}

interface TabsProps {
  items: TabItem[]
  activeKey?: string
  defaultActiveKey?: string
  onChange?: (key: string) => void
  className?: string
}

export function Tabs({
  items,
  activeKey: controlledActiveKey,
  defaultActiveKey,
  onChange,
  className,
}: TabsProps) {
  const [internalActiveKey, setInternalActiveKey] = useState(
    defaultActiveKey || items[0]?.key
  )

  const activeKey = controlledActiveKey ?? internalActiveKey

  const handleTabClick = (key: string) => {
    if (controlledActiveKey === undefined) {
      setInternalActiveKey(key)
    }
    onChange?.(key)
  }

  const activeItem = items.find((item) => item.key === activeKey)

  return (
    <div className={cn("w-full", className)}>
      {/* Tab List */}
      <div className="border-b">
        <div className="flex gap-1">
          {items.map((item) => (
            <button
              key={item.key}
              onClick={() => !item.disabled && handleTabClick(item.key)}
              disabled={item.disabled}
              className={cn(
                "relative px-4 py-2.5 text-sm font-medium transition-colors",
                "hover:text-foreground focus-visible:outline-none",
                item.key === activeKey
                  ? "text-primary"
                  : "text-muted-foreground",
                item.disabled && "cursor-not-allowed opacity-50"
              )}
            >
              {item.label}
              {item.key === activeKey && (
                <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary" />
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Tab Content */}
      <div className="pt-4">{activeItem?.children}</div>
    </div>
  )
}
