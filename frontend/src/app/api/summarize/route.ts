import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";

// Allow up to 120 seconds for Claude to process large documents
export const maxDuration = 120;

export async function POST(request: NextRequest) {
    const backendUrl = process.env.API_URL || "http://localhost:8000";

    try {
        // Forward the multipart form data as-is to the backend
        const formData = await request.formData();

        const res = await fetch(`${backendUrl}/api/summarize`, {
            method: "POST",
            body: formData,
        });

        const data = await res.json();
        return NextResponse.json(data, { status: res.status });
    } catch (error) {
        console.error("Proxy error:", error);
        return NextResponse.json(
            { error: "proxy_error", message: "Could not connect to the backend server." },
            { status: 502 }
        );
    }
}
