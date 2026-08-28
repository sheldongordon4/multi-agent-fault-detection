export type FormErrors = Partial<Record<string, string[]>>;

// Map Axios error responses into field-based errors for forms
type AxiosLikeError = {
    response?: {
        status: number;
        data?: Record<string, unknown>;
    };
    code?: string;
    message?: string;
};

function isRecord(value: unknown): value is Record<string, unknown> {
    return typeof value === "object" && value !== null;
}

export function mapAxiosErrorToFieldErrors(error: unknown): FormErrors {
    const axiosError: AxiosLikeError = isRecord(error)
        ? (error as AxiosLikeError)
        : {};

    const toField = (key: string, msg: string): FormErrors => ({
        [key]: [msg],
    });

    // Network or request-level errors
    if (!axiosError.response) {
        if (
            axiosError.code === "NETWORK_ERROR" ||
            axiosError.message?.includes("Network Error")
        ) {
            return toField(
                "general",
                "Network error. Please check your internet connection.",
            );
        }
        if (
            axiosError.code === "ECONNABORTED" ||
            axiosError.message?.includes("timeout")
        ) {
            return toField("general", "Request timeout. Please try again.");
        }
        return toField("general", "Connection error. Please try again.");
    }

    const { status, data } = axiosError.response;
    const responseText = (key: string): string | undefined =>
        typeof data?.[key] === "string" ? data[key] : undefined;

    // Common  validation structure: { errors: { field: [messages] } }
    const normalizedFieldErrors = (): FormErrors | null => {
        if (!data?.errors) return null;
        const fe: FormErrors = {};
        for (const [field, messages] of Object.entries(data.errors)) {
            if (!messages) continue;
            fe[field] = Array.isArray(messages) ? messages : [String(messages)];
        }
        return fe;
    };

    switch (status) {
        case 400:
        case 422: {
            const fe = normalizedFieldErrors();
            if (fe && Object.keys(fe).length > 0) return fe;
            if (responseText("message")) return toField("general", responseText("message")!);
            if (responseText("detail")) return toField("general", responseText("detail")!);
            return toField(
                "general",
                "Invalid request. Please check your input.",
            );
        }
        case 401:
            // Auth-specific: surface under password to show near the form
            return toField(
                "password",
                responseText("message") || "Invalid credentials. Please try again.",
            );
        case 403:
            return toField("general", responseText("message") || "Access forbidden.");
        case 404:
            return toField("general", "Resource not found. Please try again.");
        case 409:
            // If backend sends a conflict without field details, attach to email by default for auth flows
            return toField(
                "email",
                responseText("message") ||
                    "Conflict error. This resource may already exist.",
            );
        case 429:
            return toField(
                "general",
                "Too many requests. Please try again later.",
            );
        case 500:
            return toField("general", "Server error. Please try again later.");
        case 502:
        case 503:
        case 504:
            return toField(
                "general",
                "Service temporarily unavailable. Please try again later.",
            );
        default:
            if (responseText("message")) return toField("general", responseText("message")!);
            if (responseText("detail")) return toField("general", responseText("detail")!);
            return toField(
                "general",
                `An error occurred (${status}). Please try again.`,
            );
    }
}
