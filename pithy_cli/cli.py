import typer

app = typer.Typer()

@app.command()
def hello():
    typer.echo("Hello from pithy!")

@app.command()
def goodbye():
    typer.echo("See ya!")

if __name__ == "__main__":
    app()
