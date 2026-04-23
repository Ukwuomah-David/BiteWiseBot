from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route("/")
def home():
    return "BiteWise webhook is live 🚀"

@app.route("/paystack-webhook", methods=["POST"])
def webhook():
    try:
        data = request.json

        print("Webhook received:", data)

        if data and data.get("event") == "charge.success":
            metadata = data["data"].get("metadata", {})
            telegram_id = metadata.get("telegram_id")

            if telegram_id:
                print(f"Upgrade user {telegram_id} to premium")

        return jsonify({"status": "ok"}), 200

    except Exception as e:
        print("Webhook error:", e)
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    import os

    port = int(os.environ.get("PORT", 10000))

    app.run(host="0.0.0.0", port=port)
