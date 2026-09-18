import PaperDetailClient from "@/components/PaperDetailClient";

export default async function PaperDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <PaperDetailClient paperId={id} />;
}
