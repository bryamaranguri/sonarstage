import { RackUnit, Rack, Lcd } from "../components/hardware";

export default function MatrixPage() {
  return (
    <>
      <div className="header-strip center">
        <div className="hs-title">MATRIZ DE PARTES</div>
      </div>
      <Rack>
        <RackUnit title="MATRIZ DE PARTES" subtitle="Próxima entrega">
          <Lcd className="lcd-wide">
            <div className="lcd-row"><span className="lcd-key">PRÓXIMA ENTREGA</span></div>
            <div className="lcd-big">Línea de tiempo por stem · tocar o secuencia</div>
            <div className="lcd-row dim">Por ahora: python -m sonarstage_import.parts</div>
          </Lcd>
        </RackUnit>
      </Rack>
    </>
  );
}
