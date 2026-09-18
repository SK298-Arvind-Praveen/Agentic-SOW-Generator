import { toast as baseToast, ToastContent, ToastOptions, Id, UpdateOptions } from 'react-toastify';

// Errors represent actionable failures. Keep them visible until the user
// explicitly dismisses them, regardless of the timeout requested by a caller.
const persistentError = (content: ToastContent, options: ToastOptions = {}) => (
  baseToast.error(content, {
    ...options,
    autoClose: false,
    closeButton: true,
    closeOnClick: false,
    draggable: false,
  })
);

const persistentUpdate = (toastId: Id, options: UpdateOptions) => (
  baseToast.update(
    toastId,
    options.type === 'error'
      ? {
          ...options,
          autoClose: false,
          closeButton: true,
          closeOnClick: false,
          draggable: false,
        }
      : options,
  )
);

export const toast = new Proxy(baseToast, {
  get(target, property, receiver) {
    if (property === 'error') return persistentError;
    if (property === 'update') return persistentUpdate;
    return Reflect.get(target, property, receiver);
  },
}) as typeof baseToast;
