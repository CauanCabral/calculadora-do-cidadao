from datetime import date
from re import sub
from typing import Dict, Optional, Union

from aiohttp import ClientSession
from bs4 import BeautifulSoup
from requests import post


class ÍndiceInválido(Exception):
    pass


class BaseDaCalculadoraDoCidadão:

    URL_DO_FORMULÁRIO = (
        "https://www3.bcb.gov.br/"
        "CALCIDADAO/publico/corrigirPorIndice.do?method=corrigirPorIndice"
    )

    ÍNDICES = {
        "00189IGP-M": "IGP-M (FGV) - a partir de 06/1989",
        "00190IGP-DI": "IGP-DI (FGV) - a partir de 02/1944",
        "00188INPC": "INPC (IBGE) - a partir de 04/1979",
        "00433IPCA": "IPCA (IBGE) - a partir de 01/1980",
        "10764IPC-E": "IPCA-E (IBGE) - a partir de 01/1992",
        "00191IPC-BRASIL": "IPC-BRASIL (FGV) - a partir de 01/1990",
        "00193IPC-SP": "IPC-SP (FIPE) - a partir de 11/1942",
    }
    ÍNDICE_PADRÃO = "00189IGP-M"

    def __init__(
        self, índice: Optional[str] = None, verificar_ssl: bool = True
    ) -> None:
        índice = índice or self.ÍNDICE_PADRÃO
        if not índice in self.ÍNDICES:
            válidos = ", ".join(self.ÍNDICES)
            raise ÍndiceInválido(
                f"{índice} não é um índice válido. Utilize um desses: {válidos}"
            )

        self.verificar_ssl = verificar_ssl
        self.dados_do_formulário = {
            "aba": "1",
            "selIndice": self.ÍNDICE_PADRÃO,
            "idIndice": "",
            "nomeIndicePeriodo": "",
        }

    @staticmethod
    def preparar_data(data: Optional[date] = None) -> str:
        data = data or date.today()
        return f"{data.month:0>2d}/{data.year}"

    @staticmethod
    def limpar_chave(texto: str) -> str:
        texto = sub(r"\s+", " ", texto)
        return texto.strip()

    @staticmethod
    def limpar_valor(texto: str) -> Union[str, date, float, None]:
        texto = sub(r"[^\d,/%]", "", texto)

        if "%" in texto:
            return None

        if "," in texto:
            texto = texto.replace(",", ".")
            return float(texto)

        if "/" in texto:
            mês, ano = texto.split("/")
            return date(int(ano), int(mês), 1)

        return texto

    def parser(self, content: str) -> Dict[str, Union[str, date, float]]:
        html = BeautifulSoup(content, "html.parser")
        nós = html.find_all("td", class_="fundoPadraoAClaro3")
        textos = tuple(nó.text for nó in nós)
        dados = {
            self.limpar_chave(chave): self.limpar_valor(valor)
            for chave, valor in zip(textos[::2], textos[1::2])
        }
        return {chave: valor for chave, valor in dados.items() if valor}

    def dados_para_requisição(
        self, valor: float, data_original: date, data_final: date
    ) -> Dict[str, str]:
        dados = self.dados_do_formulário.copy()
        dados.update(
            {
                "dataInicial": self.preparar_data(data_original),
                "dataFinal": self.preparar_data(data_final),
                "valorCorrecao": f"{valor:.2f}".replace(".", ","),
            }
        )
        return dados


class CalculadoraDoCidadão(BaseDaCalculadoraDoCidadão):
    def __call__(
        self, valor: float, data_original: date, data_final: Optional[date] = None
    ) -> Dict[str, Union[str, float, date]]:
        data_final_corrigida = data_final or date.today()
        resposta = post(
            self.URL_DO_FORMULÁRIO,
            data=self.dados_para_requisição(valor, data_original, data_final_corrigida),
            verify=self.verificar_ssl,
        )
        return self.parser(resposta.text)


class CalculadoraDoCidadãoAsyncio(BaseDaCalculadoraDoCidadão):
    async def __call__(
        self,
        sessão: ClientSession,
        valor: float,
        data_original: date,
        data_final: Optional[date] = None,
    ) -> Dict[str, Union[str, float, date]]:
        data_final_corrigida = data_final or date.today()
        dados = self.dados_para_requisição(valor, data_original, data_final_corrigida)
        kwargs = {"data": dados, "ssl": self.verificar_ssl}
        async with sessão.post(self.URL_DO_FORMULÁRIO, **kwargs) as resposta:
            return self.parser(await resposta.text())
