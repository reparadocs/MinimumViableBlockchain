from flask import Flask, request

app = Flask(__name__)

all_signals = []

@app.route("/", methods=['POST', 'GET'])
def hello():
  return "hello world"

@app.route("/signals", methods=['POST', 'GET'])
def signals():
  if request.method == 'POST':
    all_signals.append(request.form['signal'])
    return "true"
  else:
    return str(len(all_signals))

@app.route("/signal/<signal_id>")
def signal(signal_id):
  return all_signals[int(signal_id)]

@app.route("/all")
def all():
  s = ""
  for signal in all_signals:
    s += signal + "\n"
  return s

if __name__ == "__main__":
  app.run()

