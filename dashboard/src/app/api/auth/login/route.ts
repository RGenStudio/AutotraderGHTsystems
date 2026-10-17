import { NextRequest, NextResponse } from "next/server";
import {
  AUTH_COOKIE,
  cookieOptions,
  createSessionToken,
  verifyPassword,
} from "@/lib/auth";

export async function POST(request: NextRequest) {
  let password = "";
  const contentType = request.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    const body = (await request.json()) as { password?: string };
    password = body.password ?? "";
  } else {
    const form = await request.formData();
    password = String(form.get("password") ?? "");
  }

  if (!verifyPassword(password)) {
    return NextResponse.json({ error: "invalid_password" }, { status: 401 });
  }

  const token = await createSessionToken();
  const response = NextResponse.json({ ok: true });
  response.cookies.set(AUTH_COOKIE, token, cookieOptions());
  return response;
}
