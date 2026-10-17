'use client';

import { useState } from 'react';
import Image from 'next/image';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { ArrowLeft, ArrowRight, ImagePlus, Loader2, Star, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { getErrorMessage } from '@/lib/api';
import {
  useAddItemImage,
  useDeleteItemImage,
  useReorderItemImages,
  useSetPhotoView,
  useSetPrimaryImage,
} from '@/lib/hooks/use-items';
import { usePhotoTypeLabel } from '@/lib/hooks/use-translated-constants';
import { ACCEPTED_IMAGE_INPUT } from '@/lib/image-types';
import { PHOTO_TYPES, type Item, type PhotoType } from '@/lib/types';
import { cn } from '@/lib/utils';

// Front and back are taken by one photo each; new photos fill whichever is still free.
export function nextFreeView(taken: (PhotoType | null | undefined)[]): PhotoType | null {
  if (!taken.includes('front')) return 'front';
  if (!taken.includes('back')) return 'back';
  return null;
}

interface ManagedPhoto {
  // null is the cover, which lives on the item itself.
  imageId: string | null;
  src: string;
  view: PhotoType | null;
}

// Edit-mode photo list for an item: label each photo, pick the cover, reorder, delete, add more.
export function PhotoManager({ item, maxPhotos = 10 }: { item: Item; maxPhotos?: number }) {
  const t = useTranslations('wardrobe.photos');
  const viewLabel = usePhotoTypeLabel();
  const addImage = useAddItemImage();
  const deleteImage = useDeleteItemImage();
  const setPrimary = useSetPrimaryImage();
  const reorder = useReorderItemImages();
  const setView = useSetPhotoView();
  const [uploading, setUploading] = useState(0);
  const [toDelete, setToDelete] = useState<ManagedPhoto | null>(null);

  const extras = item.additional_images ?? [];
  const photos: ManagedPhoto[] = [
    { imageId: null, src: item.thumbnail_url || item.image_url || item.image_path, view: item.image_view ?? null },
    ...extras.map((img) => ({ imageId: img.id, src: img.thumbnail_url || img.image_url, view: img.view ?? null })),
  ];
  const busy =
    uploading > 0 ||
    addImage.isPending ||
    deleteImage.isPending ||
    setPrimary.isPending ||
    reorder.isPending ||
    setView.isPending;
  const room = maxPhotos - photos.length;

  const fail = (error: unknown) => toast.error(getErrorMessage(error, t('error')));

  const addFiles = async (files: File[]) => {
    const accepted = files.slice(0, Math.max(0, room));
    if (files.length > accepted.length) toast.warning(t('limit', { count: maxPhotos }));
    const taken = photos.map((photo) => photo.view);
    setUploading(accepted.length);
    for (const file of accepted) {
      const view = nextFreeView(taken);
      taken.push(view);
      try {
        await addImage.mutateAsync({ itemId: item.id, file, view });
      } catch (error) {
        fail(error);
      } finally {
        setUploading((n) => n - 1);
      }
    }
  };

  const move = (position: number, delta: number) => {
    const ids = extras.map((img) => img.id);
    const target = position + delta;
    if (target < 0 || target >= ids.length) return;
    [ids[position], ids[target]] = [ids[target], ids[position]];
    reorder.mutate({ itemId: item.id, imageIds: ids }, { onError: fail });
  };

  const remove = async (photo: ManagedPhoto) => {
    try {
      if (photo.imageId) {
        await deleteImage.mutateAsync({ itemId: item.id, imageId: photo.imageId });
      } else if (extras[0]) {
        // The cover cannot be dropped on its own: the first other photo takes its place, then the
        // swapped row (now holding the old cover) is deleted.
        await setPrimary.mutateAsync({ itemId: item.id, imageId: extras[0].id });
        await deleteImage.mutateAsync({ itemId: item.id, imageId: extras[0].id });
      }
    } catch (error) {
      fail(error);
    }
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium">{t('title')}</p>
        <span className="text-xs text-muted-foreground">
          {t('count', { count: photos.length, max: maxPhotos })}
        </span>
      </div>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        {photos.map((photo, index) => {
          const position = index - 1;
          return (
            <div
              key={photo.imageId ?? 'cover'}
              className={cn(
                'min-w-0 space-y-1.5 rounded-lg border bg-card p-1.5',
                index === 0 && 'border-primary/50 ring-1 ring-primary/20'
              )}
            >
              <div className="relative aspect-square overflow-hidden rounded-md bg-muted">
                <Image src={photo.src} alt={photo.view ? viewLabel(photo.view) : ''} fill className="object-cover" sizes="160px" />
                {index === 0 && (
                  <span className="absolute left-1 top-1 inline-flex items-center gap-0.5 rounded-full bg-primary px-1.5 py-0.5 text-[10px] font-medium text-primary-foreground">
                    <Star className="h-2.5 w-2.5 fill-current" />
                    {t('cover')}
                  </span>
                )}
              </div>
              <select
                aria-label={t('type')}
                disabled={busy}
                value={photo.view ?? ''}
                onChange={(e) =>
                  setView.mutate(
                    { itemId: item.id, imageId: photo.imageId, view: (e.target.value || null) as PhotoType | null },
                    { onError: fail }
                  )
                }
                className="h-9 w-full rounded-md border bg-background px-2 text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <option value="">{t('noView')}</option>
                {PHOTO_TYPES.map((type) => (
                  <option key={type} value={type}>
                    {viewLabel(type)}
                  </option>
                ))}
              </select>
              <div className="flex items-center justify-between gap-0.5">
                {photo.imageId ? (
                  <>
                    <Button
                      type="button"
                      size="icon"
                      variant="ghost"
                      className="h-8 w-8"
                      disabled={busy}
                      aria-label={t('makeCover')}
                      title={t('makeCover')}
                      onClick={() => setPrimary.mutate({ itemId: item.id, imageId: photo.imageId! }, { onError: fail })}
                    >
                      <Star className="h-4 w-4" />
                    </Button>
                    <Button
                      type="button"
                      size="icon"
                      variant="ghost"
                      className="h-8 w-8"
                      disabled={busy || position === 0}
                      aria-label={t('previous')}
                      onClick={() => move(position, -1)}
                    >
                      <ArrowLeft className="h-4 w-4" />
                    </Button>
                    <Button
                      type="button"
                      size="icon"
                      variant="ghost"
                      className="h-8 w-8"
                      disabled={busy || position === extras.length - 1}
                      aria-label={t('next')}
                      onClick={() => move(position, 1)}
                    >
                      <ArrowRight className="h-4 w-4" />
                    </Button>
                  </>
                ) : (
                  <span className="truncate px-1 text-[11px] text-muted-foreground">{t('coverHint')}</span>
                )}
                <Button
                  type="button"
                  size="icon"
                  variant="ghost"
                  className="h-8 w-8 text-destructive hover:text-destructive"
                  disabled={busy || photos.length === 1}
                  aria-label={t('remove')}
                  title={photos.length === 1 ? t('lastPhoto') : t('remove')}
                  onClick={() => setToDelete(photo)}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            </div>
          );
        })}
        {room > 0 && (
          <label
            className={cn(
              'flex aspect-square cursor-pointer flex-col items-center justify-center gap-1 rounded-lg border-2 border-dashed border-primary/30 bg-primary/5 text-center text-xs text-primary transition-colors hover:border-primary/60 hover:bg-primary/10',
              busy && 'pointer-events-none opacity-60'
            )}
          >
            {uploading > 0 ? <Loader2 className="h-5 w-5 animate-spin" /> : <ImagePlus className="h-5 w-5" />}
            <span>{uploading > 0 ? t('uploading', { count: uploading }) : t('add')}</span>
            <input
              type="file"
              accept={ACCEPTED_IMAGE_INPUT}
              multiple
              className="sr-only"
              disabled={busy}
              onChange={(e) => {
                const files = Array.from(e.target.files ?? []);
                e.target.value = '';
                if (files.length) void addFiles(files);
              }}
            />
          </label>
        )}
      </div>

      <AlertDialog open={toDelete !== null} onOpenChange={(open) => !open && setToDelete(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('removeTitle')}</AlertDialogTitle>
            <AlertDialogDescription>{t('removeDescription')}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('keep')}</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => {
                if (toDelete) void remove(toDelete);
                setToDelete(null);
              }}
            >
              {t('remove')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
