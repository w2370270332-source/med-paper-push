import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";

export async function createServerSupabase() {
  const cookieStore = await cookies();
  return createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return cookieStore.getAll();
        },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value, options }) =>
            cookieStore.set(name, value, options),
          );
        },
      },
    },
  );
}

export async function getSession() {
  const supabase = await createServerSupabase();
  const { data } = await supabase.auth.getSession();
  return data.session;
}

export async function getUser() {
  const supabase = await createServerSupabase();
  const { data } = await supabase.auth.getUser();
  return data.user;
}

export async function isAdmin() {
  const supabase = await createServerSupabase();
  const { data } = await supabase.auth.getUser();
  return data.user?.app_metadata?.role === "admin";
}
