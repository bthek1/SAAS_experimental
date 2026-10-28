import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"

interface ConfirmDeleteDialogProps {
  /** What is being deleted, e.g. "questionnaire type". `null` closes the dialog. */
  itemLabel: string | null
  onConfirm: () => void
  onCancel: () => void
  isPending: boolean
  /** Shown inside the dialog, e.g. the API's 409 "in use" message. */
  error?: string | null
}

export function ConfirmDeleteDialog({
  itemLabel,
  onConfirm,
  onCancel,
  isPending,
  error,
}: ConfirmDeleteDialogProps) {
  return (
    <Dialog open={itemLabel !== null} onOpenChange={(open) => !open && onCancel()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Delete {itemLabel}?</DialogTitle>
          <DialogDescription>This action cannot be undone.</DialogDescription>
        </DialogHeader>
        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={onCancel}>
            Cancel
          </Button>
          <Button variant="destructive" onClick={onConfirm} disabled={isPending}>
            {isPending ? "Deleting…" : "Delete"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
