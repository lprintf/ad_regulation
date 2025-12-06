import { Toaster as SonnerToaster, toast as sonnerToast } from "sonner"

export function Toaster() {
  return (
    <SonnerToaster
      position="top-center"
      toastOptions={{
        classNames: {
          toast: "bg-background text-foreground border shadow-lg",
          title: "text-foreground font-medium",
          description: "text-muted-foreground",
          success: "border-success/30 bg-success/10",
          error: "border-destructive/30 bg-destructive/10",
          warning: "border-yellow-500/30 bg-yellow-500/10",
          info: "border-primary/30 bg-primary/10",
        },
      }}
    />
  )
}

export const toast = {
  success: (content: string) => sonnerToast.success(content),
  error: (content: string) => sonnerToast.error(content),
  warning: (content: string) => sonnerToast.warning(content),
  info: (content: string) => sonnerToast.info(content),
  loading: (content: string) => sonnerToast.loading(content),
  dismiss: (id?: string | number) => sonnerToast.dismiss(id),
}
