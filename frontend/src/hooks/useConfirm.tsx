import { useState, useCallback } from "react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

type ConfirmOptions = {
  title: string;
  description?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: "default" | "destructive";
};

type ConfirmState = ConfirmOptions & {
  resolve: (value: boolean) => void;
};

export function useConfirm(): [
  (options: ConfirmOptions) => Promise<boolean>,
  JSX.Element,
] {
  const [state, setState] = useState<ConfirmState | null>(null);

  const confirm = useCallback((options: ConfirmOptions): Promise<boolean> => {
    return new Promise((resolve) => {
      setState({ ...options, resolve });
    });
  }, []);

  const handleClose = useCallback((value: boolean) => {
    state?.resolve(value);
    setState(null);
  }, [state]);

  const dialog = (
    <AlertDialog open={state !== null} onOpenChange={(open) => { if (!open) handleClose(false); }}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{state?.title}</AlertDialogTitle>
          {state?.description && (
            <AlertDialogDescription>{state.description}</AlertDialogDescription>
          )}
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel onClick={() => handleClose(false)}>
            {state?.cancelLabel ?? "ยกเลิก"}
          </AlertDialogCancel>
          <AlertDialogAction
            onClick={() => handleClose(true)}
            className={state?.variant === "destructive" ? "bg-red-600 hover:bg-red-700" : ""}
          >
            {state?.confirmLabel ?? "ยืนยัน"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );

  return [confirm, dialog];
}
