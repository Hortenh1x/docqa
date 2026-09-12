import { AccountScreen } from "@/features/account/AccountScreen";
export default async function AccountActionPage({ params }: { params: Promise<{ action: string }> }) {
  const { action } = await params;
  return <AccountScreen key={action} action={action} />;
}
